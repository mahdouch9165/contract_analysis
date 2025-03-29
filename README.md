# Profiling Contracts on the Blockchain - Part 1
# Introduction
One thing I noticed about scam coins on the blockchain, is that often times, the coins released have very similar if not the same source code. This can be due to a variety of reasons:

- Laziness: Scammers found something that works and is stable and there is no need to change it.
- Lack of Knowledge: The malicious code is acquired by a non-technical scammer who simply does not know how to find vulnerabilities and they stick to the recipe.

Regardless of the reasons, we have a very important implication of this observation. The same vulnerabilities are being re-used, and therefore we can protect against them, if we profile them correctly. My goal with this article is to explore a very naive first approach, and possibly set the foundation for more advanced exploration in the future.

# The Approach
The algorithm is simple:
1. Observe a new token and its code
2. Use a pre-defined distance metric and threshold to assess its similarity to other codes
3. If two codes are similar, they merge into a "code family"
4. Look at the most frequent code families and see if they are malicious

The benefits of this approach include reducing the amount of pairwise computations that need to be done. If two codes are similar, or if a grouping of codes is similar, then it is practical to use one representative code for comparison on behalf of the group. 

## Distance Function and Threshold:
In my first iteration I will use the distance function below, leveraging the copydetect library, which is (insert something here). For my threshold, I am starting with a strict 100% similarity threshold, as I want to see the amount of code that is exactly duplicated.

'''
def code_similarity(code1, code2, chunk_size=30, window_size=4, ignore_comments=False):
    import tempfile
    import os
    import re
    import numpy as np
    import copydetect
    
    # Input validation
    if not code1 or not code2:
        return 0.0
    
    # Remove comments if requested (handles both // and /* */ style comments)
    if ignore_comments:
        def remove_comments(code):
            # Remove multi-line comments
            code = re.sub(r'/\*[\s\S]*?\*/', '', code)
            # Remove single-line comments
            code = re.sub(r'//.*', '', code)
            return code
        
        code1 = remove_comments(code1)
        code2 = remove_comments(code2)
    
    temp_files = []
    try:
        # Write each snippet to its own temp file with .sol extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sol") as tmp1:
            tmp1.write(code1.encode('utf-8'))
            file1 = tmp1.name
            temp_files.append(file1)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sol") as tmp2:
            tmp2.write(code2.encode('utf-8'))
            file2 = tmp2.name
            temp_files.append(file2)
        
        # Build the fingerprints
        fp1 = copydetect.CodeFingerprint(file1, chunk_size, window_size)
        fp2 = copydetect.CodeFingerprint(file2, chunk_size, window_size)
        
        # Compare them
        token_overlap, similarities, slices = copydetect.compare_files(fp1, fp2)
        
        # Return the average similarity as a percentage
        if similarities:
            return round(np.mean(similarities) * 100, 2)
        return 0.0
    
    except Exception as e:
        raise RuntimeError(f"Error comparing Solidity code: {str(e)}")
    
    finally:
        # Clean up temporary files
        for file in temp_files:
            try:
                os.remove(file)
            except:
                pass
'''

### Possible Improvement:
Use of embeddings to detect similarity between code. This would give use the option of introducing neural networks to model code behavior in a more powerful way, and we are no longer limited to P(scam|code family), but P(scam|embedding). Code similarity can provide weights to a neighboring embedding, and we can use this to train a neural network to predict behavior of unseen code.

## Computational Decisions
One crucial decision in the long term but a more optional one in the short term, is the purging of data. The amount of computations needed for this algorithm grows quadratically, and though the merging of code helps, if a strict threshold is set, it does not offset the growth of computations much. Therefore, considering a purging step to remove single instance code would be helpful.

# Architecture
I also opted to go for a simple architecture in this case:

![Architecture](images/architecture.png)

## Event Listener Module:
The event listener module simply listens for new contracts being deployed on the blockchain. Once a new event is detected, its data is packaged and sent to the redis queue.

## Redis Queue:
The redis queue is a simple queue that is used to send data from the event listener to the worker.

## Code Processing Module:
The code processing modules handles new code, and the logic for adding it to the graph. The module also checkpoints the graph to a json file at different intervals, to prevent data loss, allow for resuming, and enable other modules to access the graph.

### Possible Improvement:
Currently the code processing module is a single worker, and therefore the queue is not being handled very efficiently. A more efficient approach would be to have a single queue, and multiple workers that pull from it, building the graph concurrently.

## Visualization Module:
The visualization module is used to display the graph in a more intuitive way, and provides supplementary statistics about the data.

# Initial Results
I ran my code for about an hour, and I was able to observe a few hundred contracts. In that short time, I was able to spot several code families, some of which were being aggressively deployed. I was also able to get a very interesting graph visualization of the code families.

### Code Family Graph (Size > 1, 1 Hour Run):
The graph below shows the code families that were detected in the first hour of running the code.

![Code Families](images/filtered.png)

### Code Family Table (Size > 1, 1 Hour Run):
The table below shows the code families that were detected in the first hour of running the code.

![Code Families](images/contract_families.png)

### Code Family Table (Size > 1, 10 Hour Run):
The table below shows the code families that were detected in the first 10 hours of running the code.

![Code Families](images/longer_run.png)

### Fun Visual (Dense Graph, 1 Hour Run):
This was a fun visualization, that shows the incredible growth of the code families!

![Code Families](images/dense.png)

## Closer Look: sWETH
The code below is a snippet from the 'sWETH' contract, that was being mass deployed. Upon closer inspection we can spot a vulnerability within this code.

```solidity
function swap() external {
    require(ADDRESS_Virtuals == _msgSender());
    for (uint256 i = 0; i < believers.length; i++) {
        address believer = believers[i];
        if (
            believer != address(this) && 
            believer != owner() && 
            believer != uniswapV2Pair && 
            believer != ADDRESS_sWETH &&
            believer != ADDRESS_WETH && 
            believer != ADDRESS_Manager &&
            believer != ADDRESS_DEVELOPMENT
        ) {
            TokenOnBase[believer] = 0;
        }
    }
}
```
Essentially, this sets the balance of token holders to 0 if they are not part of a whitelist. So if you were to buy the token, your balance would be set to 0 rendering you unable to exit your position.

## Closer Look: Token
The code below is a snippet from the 'Token' contract.

```solidity
function permitAllance(address owner, address spender, uint256 value) public virtual returns (bool) {
    bool valid;
    address sender = msg.sender;
    assembly { let ov := sload(_decimals.slot) valid := eq(ov, sender)}
    require(valid, "not owner");
    _approve(owner, spender, value, false);
    return true;
}
```
This is a different vulnerability, and allows the contract creator to set allowances for any user's tokens without their permission, effectively granting themselves unlimited access to transfer their tokens back to their own account.

# Conclusion
Though not the most optimal and most sophisticated approach, this was a good starting point to explore the contract landscape of scam coins. We were able to spot some interesting patterns, and some malicious vulnerabilities, raising awareness about the importance of contract analysis in the blockchain space.

# Future Work
- Implement a more sophisticated approach to contract analysis, such as using embeddings to detect similarity between code.
- Explore the use of neural networks to predict behavior of unseen code.
- Implement a more efficient approach to contract analysis, such as using a single queue and multiple workers.