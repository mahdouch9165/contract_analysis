# Profiling Contracts on the Blockchain - Part 1
# Introduction
A notable observation regarding scam tokens on blockchain networks is that they often utilize identical or highly similar source code. This can be due to a variety of reasons:

- Convenience: Scammers re-use stable, proven malicious code without modification.
- Limited Technical Knowledge: Non-technical scammers rely on pre-existing malicious templates due to their lack of expertise in coding vulnerabilities.

The implication is clear: repeated vulnerabilities can be systematically identified and mitigated through accurate code profiling. This articles explores a naive approach to profiling smart contract code, aiming to build a foundation for more sophisticated future exploration.

# Methodology
The approach is as follows:

1. Monitor tokens (smart contracts) deployments on the blockchain
2. Extract smart contract code for each observed token
3. Use a distance metric to assess code similarity
4. Similar codes are merged into a "code family"
5. Analyze the most frequent code families for malicious patterns

One advantage of this approach is that the merging step reduces the amount of pairwise comparisons needed. Contracts within a family can be represented by a single instance for subsequent computations.

## Distance Function and Threshold
In my first iteration I will use the distance function below, leveraging the copydetect library, a plagiarism detection tool for code similarity. For my threshold, I am starting with a strict 100% similarity threshold, as I am currenlty only interested in exact duplicates.

```python
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
```

## Potential Improvements
### Distance Metric
A more robust future improvement involves using embeddings to quantify code similarity. Currently, we cannot determine the probability of a scam for an unseen code, we can only do so for code belonging to established families. 

$$ P(scam|code) = \sum_{f \in families} (P(scam|f) \cdot 1 \text{ if } code \in f)$$

Embeddings would enable us to determine the probability of a scam for an unseen code, using what we have already observed. One way to do this is by using a weighted average, for example:

$$P(scam|embedding) = \frac{\sum_{f \in families} P(scam|f) \cdot \max(0, cosine(f, embedding))}{\sum_{f \in families} \max(0, cosine(f, embedding))}$$

Other approaches could be to use a neural network to predict the probability of a scam for an unseen code.

### Computational Efficiency
A critical scalability factor involves handling computational complexity, which grows quadratically with the number of contracts. While grouping similar code mitigates some computational strain, a strict similarity threshold reduces the effectiveness of this strategy. Introducing periodic data purging, especially for unique or infrequent code instances, could significantly enhance computational efficiency.

# Architecture
The architecture for the implemenation is as follows:

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
This preliminary investigation successfully demonstrates the feasibility of profiling smart contract code to identify malicious contracts. We were able to spot some interesting patterns, and some code vulnerabilities, raising awareness about the importance of contract analysis in the blockchain space.

# Future Work
- Implement a more sophisticated approach to contract analysis, such as using embeddings to detect similarity between code.
- Explore the use of neural networks to predict behavior of unseen code.
- Implement a more efficient approach to contract analysis, such as using a single queue and multiple workers.