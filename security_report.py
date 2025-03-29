import json
from src.modules.utils.function_names import *

class Checks:
    def __init__(self, code):
        raise NotImplementedError
    
    def check(self):
        raise NotImplementedError

class SecurityFunctionPresence(Checks):
    def __init__(self, code):
        self.code = code
        # Get contract code
        self.functions = get_function_names(self.code)
        self.bad_functions = ["permitAllance", "_burn", "isOwner", "mod", "getHolders", "_math", "tokenSymbol", "tokenDecimals", "swap", "executeSwap", "ERC20Coefficient", "addToBlacklist", "enableTrading", "removeLimits"]
        self.warning_functions = ["claimGas"]
        self.function_combos = [("claim", "multicall", "execute")]
        self.functions_set = set()
    def check(self):
        for warning_function in self.warning_functions:
            if warning_function in self.functions:
                self.functions_set.add(warning_function)

        for bad_function in self.bad_functions:
            if bad_function in self.functions:
                self.functions_set.add(bad_function)
            
        for combo in self.function_combos:
            if all([f in self.functions for f in combo]):
                self.functions_set.add(combo)
        return self.functions_set

class SecurityBadLines(Checks):
    def __init__(self, code):
        self.code = code
        # Get contract code
        self.warning_lines = ["library Address"]
        self.bad_lines = ["_p76234"]
        self.lines_set = set()
    def check(self):
        for line in self.warning_lines:
            if line in self.contract_code:
                self.lines_set.add(line)
        
        for line in self.bad_lines:
            if line in self.contract_code:
                self.lines_set.add(line)
        return self.lines_set

def main():
    data_path = "data/contract_families.json"
    with open(data_path, "r") as f:
        data = json.load(f)

    rows = []
    for family in data["families"]:
        id = family["id"]
        code = family["code"]
        functions = SecurityFunctionPresence(code).check()
        lines = SecurityBadLines(code).check()
        rows.append({
            "id": id,
            "functions": functions,
            "lines": lines
        })

    # make df 
    df = pd.DataFrame(rows)

    # 
    
if __name__ == "__main__":
    main()