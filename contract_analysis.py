import json
import redis
from src.modules.w3.chains.scanner.base_scanner import BaseScanner

class ContractFamily:
    def __init__(self, contract):
        self.code = contract.code
        self.count = 1
        self.addresses = [contract.address]
        self.names = set([contract.name])

    def add_contract(self, contract):
        self.count += 1
        self.addresses.append(contract.address)
        self.names.add(contract.name)

    def code_similarity(code1, code2, chunk_size=30, window_size=4):
        """
        Returns a percentage indicating how similar the two code strings are,
        using CopyDetect under the hood.
        
        Requirements:
            pip install copydetect
        
        Parameters:
            code1 (str): First code snippet as a string.
            code2 (str): Second code snippet as a string.
            chunk_size (int): Number of tokens in each chunk for fingerprinting.
            window_size (int): Sliding window size for building winnowed fingerprints.

        Returns:
            float: Highest similarity percentage between the two code snippets.
        """
        import tempfile
        import copydetect

        # If either snippet is empty, similarity is 0
        if not code1 or not code2:
            return 0.0

        # Write each snippet to its own temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp1:
            tmp1.write(code1.encode('utf-8'))
            file1 = tmp1.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp2:
            tmp2.write(code2.encode('utf-8'))
            file2 = tmp2.name

        # Build the fingerprints
        fp1 = copydetect.CodeFingerprint(file1, chunk_size, window_size)
        fp2 = copydetect.CodeFingerprint(file2, chunk_size, window_size)

        # Compare them
        token_overlap, similarities, slices = copydetect.compare_files(fp1, fp2)
        
        # Return the highest similarity as a percentage
        if similarities:
            return round(max(similarities) * 100, 2)
        return 0.0

    def is_similar(self, contract, threshold=100):
        similarity = self.code_similarity(self.code, contract.code)
        conclusion = similarity > threshold
        return similarity, conclusion

class Contract:
    def __init__(self, address, code, name):
        self.address = address
        self.code = code
        self.name = name

class ContractAnalysis:
    ETH = "0x4200000000000000000000000000000000000006"

    def __init__(self, scanner):
        from collections import defaultdict
        self.scanner = scanner
        self.families = []
        self.graph = defaultdict(defaultdict(float))

    def find_weth_token(self, event_data):
            # Decide which token is which
            address_0 = event_data["token0"]
            address_1 = event_data["token1"]
            if address_0 == self.ETH:
                return address_1
            elif address_1 == self.ETH:
                return address_0
            else:
                return None

    def handle_event(self, event):
        #1. get the address of a given token
        address = self.find_weth_token(event)
        if address is None:
            return
        #2. get the code of the token
        code, name = self.scanner.get_contract_source_code_and_name(address)
        
        #3 create a contract
        contract = Contract(address, code, name)

        # compare to other families
        from tqdm import tqdm
        observations = {}
        for family in tqdm(self.families):
            similarity, conclusion = family.is_similar(contract)
            if conclusion:
                family.add_contract(contract)
                return
            observations[family] = similarity
            
        # if no family is found, create a new one
        family = ContractFamily(contract)
        self.families.append(family)

        # update graph with observations
        for other, similarity in observations.items():
            self.graph[family][other] = similarity

r = redis.Redis(host='localhost', port=6379, db=2)

def main(contract_analysis: ContractAnalysis):
    while True:
        # Block until there is a new event in the queue
        _, event_json = r.brpop("NewToken")
        event_data = json.loads(event_json)
        contract_analysis.handle_event(event_data)

if __name__ == "__main__":
    scanner = BaseScanner()
    contract_analysis = ContractAnalysis(scanner=scanner)
    main(contract_analysis)
 