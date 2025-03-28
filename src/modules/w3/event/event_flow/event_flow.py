import logging
import os
from ...exchange.token.token import Token
from ...exchange.pair.pair import Pair
from ...exchange.exchange import to_base_units, from_base_units
from ..event import Event
from ..security.security_manager import *
from ..llm.llm_manager import LLMManager
from ..code_similarity.code_similarity_manager import *
from decimal import Decimal, getcontext
import time
import json

getcontext().prec = 28


class EventFlow:
    def __init__(self, w3, scanner, exchange, account):
        self.w3 = w3
        self.scanner = scanner
        self.exchange = exchange
        self.account = account
        self.directory = None

    def handle_event(self, event_data):
        raise NotImplementedError
    
    def setup_logs(self):
        raise NotImplementedError
    
    def get_total_account_value_eth(self):
        eth_balance = self.w3.get_eth_balance(self.account.address)
        weth_balance = self.weth.get_balance(self.account.address)
        eth_value = eth_balance + weth_balance
        return eth_value
    
    def get_token_logger(self, token, directory=None):
        self.logger = logging.getLogger(f'token_{token.address}')
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            # Ensure the logs directory exists
            os.makedirs(f'logs/{directory}', exist_ok=True)
            self.file_handler = logging.FileHandler(f'logs/{directory}/{token.address}.log')
            self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            self.file_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.file_handler)
    
    def find_weth_token(self, event_data):
        try:
            # Decide which token is which
            token_0_address = event_data["token0"]
            token_1_address = event_data["token1"]
            if token_0_address == self.weth_address:
                token = Token(token_1_address, self.w3, self.scanner)
                return token, False
            elif token_1_address == self.weth_address:
                token = Token(token_0_address, self.w3, self.scanner)
                return token, False
            else:
                # log general error
                self.general_error_logger.error(f"WETH not found in pair: {event_data}")
                return None, True
        except Exception as e:
            self.general_error_logger.error(f"Error during token identification: {str(e)}")
            return None, True
    
    def liquidity_check_usd(self, event):
        # Get the reserves of the pair
        liquidity = self.exchange.get_liquidity(event.pair)

        # Gather the reserves
        eth_reserves = None
        token_reserves = None

        for key in liquidity.keys():
            if key == self.weth_address:
                eth_reserves = liquidity[key]
            else:
                token_reserves = liquidity[key]
        
        # Get the price of the token in terms of WETH
        token_price_weth = self.exchange.get_price(event.token, self.weth, event.pair)

        # Get the price of eth in terms of USDC
        eth_price_usdc = self.exchange.get_price(self.weth, self.usdc, self.weth_usdc_pair)

        if token_price_weth is None or eth_price_usdc is None:
            return None

        # Get the price of the token in terms of USDC
        token_price_usdc = token_price_weth * eth_price_usdc

        # Calculate the liquidity in USDC
        eth_liquidity_usdc   = eth_reserves   * eth_price_usdc
        token_liquidity_usdc = token_reserves * token_price_usdc

        # 8. Sum total liquidity in USDC
        total_liquidity_usdc = eth_liquidity_usdc + token_liquidity_usdc

        return total_liquidity_usdc
    
    def setup_logs(self):
        os.makedirs(f'logs/{self.directory}', exist_ok=True)
        os.makedirs(f'data/{self.directory}', exist_ok=True)
        os.makedirs('data/code', exist_ok=True)
        # Configure the general error logger
        self.general_error_logger = logging.getLogger('general_errors')
        self.general_error_logger.setLevel(logging.ERROR)
        self.error_handler = logging.FileHandler(f'logs/{self.directory}/general_errors.log')
        self.error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.error_handler.setFormatter(self.error_formatter)
        self.general_error_logger.addHandler(self.error_handler)
        self.logger = None
        self.file_handler = None
        self.formatter = None
    
    def create_event(self, token, event_class = None):
        # Create the event object
        try:
            self.logger.info(f"Creating event object for token {token.address}")
            #event = HoneypotEvent(token, self.logger)
            event = event_class(token, self.logger)
            self.logger.info(f"Event object created successfully")
            return event, False
        except Exception as e:
            self.logger.error(f"Error creating event object: {str(e)}")
            return None, True
    
    def create_pair(self, token, event):
        try:
            # Create pair object
            self.logger.info(f"Creating event object for token {token.address}")
            pair = Pair(token, self.weth, self.w3, self.scanner, self.exchange)
            if not pair.is_valid:
                self.logger.warning(f"Pair object is invalid, skipping transaction")
                return None, True
            self.logger.info(f"Pair object created successfully")
            event.pair = pair
            return pair, False
        except Exception as e:
            self.logger.error(f"Error creating pair object: {str(e)}")
            return None, True
    
    def security_checks(self, event):
        try:
            # perform security checks
            security_manager = SecurityManager(event)
            flagged = security_manager.check()
            if flagged:
                self.logger.warning("Security checks flagged the event, skipping transaction")
                self.cleanup_logs(event.token.address)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error during security checks: {str(e)}")
            return True
    
    def pair_liquidity_check(self, event):
        try:
            # check liquidity of the pair
            self.logger.info(f"Checking liquidity of the pair")
            initial_liquidity = self.liquidity_check_usd(event)
            if initial_liquidity is None:
                self.logger.warning(f"Liquidity check failed, skipping transaction")
                self.cleanup_logs(event.token.address)
                return True
            elif initial_liquidity < 1:
                self.logger.warning(f"Liquidity is less than $1 {initial_liquidity}, skipping transaction")
                self.cleanup_logs(event.token.address)
                return True
            event.initial_liquidity = initial_liquidity
            self.logger.info(f"Liquidity check passed, initial liquidity: {initial_liquidity}")
            return False
        except Exception as e:
            self.logger.error(f"Error checking liquidity: {str(e)}")
            return True
    
    def llm_check(self, event):
        try:
            # Get the LLM decision
            llm_manager = LLMManager(event)
            llm_decision = llm_manager.prompt_llm()
            self.logger.info(f"LLM decision: {llm_decision}")
            return False
        except Exception as e:
            self.logger.error(f"Error during LLM processing: {str(e)}")
            return False
        
    def code_similarity_check(self, code):
        try:
            # Check code similarity
            code_sim_manager = SafeCodeSim(code)
            similarity_score = code_sim_manager.is_similar()
            self.logger.info(f"Code similarity score: {similarity_score}")
            return (similarity_score, False)
        except Exception as e:
            self.logger.error(f"Error during code similarity check: {str(e)}")
            return (None, True)
        
    def cleanup_logs(self, token_address):
        logger = logging.getLogger(f'token_{token_address}')

        # Remove all handlers from that logger
        while logger.handlers:
            h = logger.handlers[0]
            logger.removeHandler(h)
            h.close()

        # Remove the file physically
        log_file_path = f'logs/{self.directory}/{token_address}.log'
        if os.path.exists(log_file_path):
            os.remove(log_file_path)