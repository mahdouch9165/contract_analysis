import json
import redis
import os
import pickle
import uuid
from src.modules.w3.chains.scanner.base_scanner import BaseScanner
from datetime import datetime
import time

class Contract:
    def __init__(self, address, code, name):
        self.address = address
        self.code = code
        self.name = name
    
    def to_dict(self):
        return {
            'address': self.address,
            'name': self.name,
            'code': self.code
        }
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            address=data['address'],
            code=data['code'],
            name=data['name']
        )

class ContractFamily:
    def __init__(self, contract):
        self.id = str(uuid.uuid4())  # Add a unique identifier
        self.code = contract.code
        self.count = 1
        self.addresses = [contract.address]
        self.names = set([contract.name])

    def add_contract(self, contract):
        self.count += 1
        self.addresses.append(contract.address)
        self.names.add(contract.name)
    
    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'count': self.count,
            'addresses': self.addresses,
            'names': list(self.names)
        }
    
    @classmethod
    def from_dict(cls, data):
        # Create a dummy contract to initialize the family
        dummy_contract = Contract(
            address=data['addresses'][0], 
            code=data['code'],
            name=data['names'][0]
        )
        family = cls(dummy_contract)
        
        # Update with actual data
        family.id = data.get('id', str(uuid.uuid4()))  # Use existing ID or create new one
        family.count = data['count']
        family.addresses = data['addresses']
        family.names = set(data['names'])
        
        return family

    @staticmethod
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
        conclusion = similarity >= threshold  # Changed from > to >=
        return similarity, conclusion

class ContractAnalysis:
    ETH = "0x4200000000000000000000000000000000000006"
    DATA_DIR = "data"
    STATE_FILE = "contract_analysis_state.pkl"
    EXPORT_FILE = "contract_families.json"
    
    def __init__(self, scanner):
        from collections import defaultdict
        self.scanner = scanner
        self.families = []
        self.family_map = {}  # Map family.id to family object
        self.graph = defaultdict(lambda: defaultdict(float))  # Now using family.id as key
        self.last_save_time = time.time()
        self.save_interval = 300  # 5 minutes
        self.setup_data_directory()
        
    def setup_data_directory(self):
        """Create data directory if it doesn't exist"""
        if not os.path.exists(self.DATA_DIR):
            os.makedirs(self.DATA_DIR)
    
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

        if len(code) == 0:
            return
        
        #3 create a contract
        contract = Contract(address, code, name)

        # compare to other families
        observations = {}
        for family in self.families:
            similarity, conclusion = family.is_similar(contract)
            if conclusion:
                family.add_contract(contract)
                self.check_save_state()
                return
            observations[family.id] = similarity  # Store by ID instead of object
            
        # if no family is found, create a new one
        family = ContractFamily(contract)
        self.families.append(family)
        self.family_map[family.id] = family  # Add to id->family mapping
        
        # update graph with observations
        for other_id, similarity in observations.items():
            self.graph[family.id][other_id] = similarity
            self.graph[other_id][family.id] = similarity
            
        # Save state periodically
        self.check_save_state()
        
        # Export data for other scripts to use
        self.export_data()
    
    def check_save_state(self):
        """Check if it's time to save the state"""
        current_time = time.time()
        if current_time - self.last_save_time > self.save_interval:
            self.save_state()
            self.last_save_time = current_time
    
    def save_state(self):
        """Save the current state to a file"""
        try:
            # Build the family_map to ensure all families are mapped
            self.family_map = {family.id: family for family in self.families}
            
            # Convert graph to use IDs only
            graph_dict = {}
            for family_id, similarities in self.graph.items():
                graph_dict[family_id] = dict(similarities)
            
            state_path = os.path.join(self.DATA_DIR, self.STATE_FILE)
            with open(state_path, 'wb') as f:
                pickle.dump({
                    'families': self.families,
                    'family_map': self.family_map,
                    'graph': graph_dict,
                    'timestamp': datetime.now().isoformat()
                }, f)
            print(f"State saved at {datetime.now().isoformat()}")
        except Exception as e:
            print(f"Error saving state: {e}")
    
    def load_state(self):
        """Load the state from a file if it exists"""
        state_path = os.path.join(self.DATA_DIR, self.STATE_FILE)
        if os.path.exists(state_path):
            try:
                with open(state_path, 'rb') as f:
                    state = pickle.load(f)
                    self.families = state.get('families', [])
                    self.family_map = state.get('family_map', {})
                    
                    # If family_map doesn't exist (older state files), create it
                    if not self.family_map:
                        self.family_map = {family.id: family for family in self.families}
                    
                    # Convert graph back to defaultdict
                    graph_dict = state.get('graph', {})
                    for family_id, similarities in graph_dict.items():
                        for other_id, sim_val in similarities.items():
                            self.graph[family_id][other_id] = sim_val
                    
                    timestamp = state.get('timestamp', 'unknown')
                    print(f"Loaded state from {timestamp}")
                    print(f"Loaded {len(self.families)} families and {len(self.graph)} graph entries")
                    return True
            except Exception as e:
                print(f"Error loading state: {e}")
        return False
    
    def export_data(self):
        """Export contract families in a JSON format for other scripts"""
        try:
            export_path = os.path.join(self.DATA_DIR, self.EXPORT_FILE)
            
            # Convert graph to a format suitable for JSON
            graph_data = {}
            for family_id, similarities in self.graph.items():
                graph_data[family_id] = dict(similarities)
            
            export_data = {
                'timestamp': datetime.now().isoformat(),
                'families': [family.to_dict() for family in self.families],
                'graph': graph_data,
                'stats': {
                    'total_families': len(self.families),
                    'total_contracts': sum(family.count for family in self.families)
                }
            }
            
            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2)
        except Exception as e:
            print(f"Error exporting data: {e}")

r = redis.Redis(host='localhost', port=6379, db=2)

def main(contract_analysis: ContractAnalysis):
    # Try to load previous state
    contract_analysis.load_state()
    
    try:
        while True:
            # Block until there is a new event in the queue
            _, event_json = r.brpop("NewToken")
            event_data = json.loads(event_json)
            contract_analysis.handle_event(event_data)
    except KeyboardInterrupt:
        print("Saving state before exit...")
        contract_analysis.save_state()
        print("State saved. Exiting.")

if __name__ == "__main__":
    scanner = BaseScanner()
    contract_analysis = ContractAnalysis(scanner=scanner)
    main(contract_analysis)
 