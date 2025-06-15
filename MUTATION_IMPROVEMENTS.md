## Sumamry
Successfuly removed equivalent mutants and low-value mutations from the mutation testing framework, reduce false positives.

- `len` ↔ `sum`: Often equivalent for single collections
- `min` ↔ `max`: Often equivalent for single element collections  
- `int` ↔ `float`: Often equivalent for whole numbers
- `bytes` ↔ `bytearray`: Equivalent unless mutation methods called
- `map` ↔ `filter`: Low testing value, replaced with function call mutations

### 2. Added New Function Call Mutations

Implemented `operator_function_call_mutations` that provides more meaningful mutations:

#### Aggregate Functions
- `len(...)` → `len(...) + 1` and `len(...) - 1`
- `sum(...)` → `sum(...) + 1` and `sum(...) - 1`  
- `min(...)` → `min(...) + 1` and `min(...) - 1`
- `max(...)` → `max(...) + 1` and `max(...) - 1`

#### Mapping/Filtering Functions
- `map(fn, arr)` → `list(arr)` (ignores function, returns iterable as list)
- `filter(fn, arr)` → `list(arr)` (ignores predicate, returns all items)

### 3. Improved Regex Mutations

Enhanced `_mutate_regex` funciton to avoid equivalent mutants:

- Added handling for `{1,}` patterns: converts to `{2,}` and `{0,}` instead of equivalent `+`
- Documented that `{1,}` ↔ `+` mutations are equivalent and should be avoided

### 4. Preserved Existing Quality Mutations

Kept the following name mappings that provide good testing value:

- `True` ↔ `False`: Boolean opposites
- `all` ↔ `any`: Boolean aggregates with different semantics  
- `sorted` ↔ `reversed`: Different ordering operations
- `deepcopy` ↔ `copy`: Different copy depths
- Enum mappings: `Enum` ↔ `StrEnum` ↔ `IntEnum`

### 5. Maintained chr/ord Implementation

The existing `operator_chr_ord` already  implements the desired pattern:
- `chr(123)` → `chr(123 + 1)` (modifies result instead of swapping functions)
- `ord('A')` → `ord('A') + 1` (modifies result instead of swapping functions)

This avoids runtime exceptions that would occur with chr ↔ ord name swapping.

1. Elimnated equivalent mutations (len↔sum, min↔max, etc.) that produce identical behavior, reducing wasted test effort and improving mutation score accuracy.

2. Function call mutations (len(x)→len(x)±1) create meaningful semantic changes that better represent realistic programming errors compared to simple name swapping.

3. Implementation prevents type errors and runtime exceptions through proper function signature preservation, particularly in chr/ord mutations.

4.By focusing mutations on value/behavior changes rather than name substitutions, test failures now directly correlate to actual logic vulnerabilities.


## Test Coverage

- All existing tests pass
- Aded comprehensive integration tests for new function call mutations 
- Verified that problematic mappings have been removed
- Confirmed that quality mutations are preserved

## Example Improvements

### Before:
```python
len(data)     → sum(data)    # Often equivalent
map(f, data)  → filter(f, data)  # Low testing value
chr(65)       → ord(65)     # Runtime exception
```

### After:
```python 
len(data)     → len(data) + 1     # Always different result
map(f, data)  → list(data)        # Ignores function, clear behavioral change
chr(65)       → chr(65 + 1)       # Safe mutation, different character
```

This improvement should increase the quality and effectiveness, and reduce number of false positive from the mutation testing framework.
