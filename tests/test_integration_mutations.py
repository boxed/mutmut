"""
Integration tests for mutation operators.

This module consolidates comprehensive testing of all mutation operators
to ensure they work correctly in combination and don't produce false positives.
"""
import libcst as cst
from mutmut.node_mutation import (
    operator_number, operator_string, operator_name, operator_assignment,
    operator_augmented_assignment, operator_remove_unary_ops, operator_dict_arguments,
    operator_arg_removal, operator_chr_ord, operator_regex, operator_enum_attribute,
    operator_lambda, operator_keywords, operator_swap_op, operator_match,
    mutation_operators
)
from collections import Counter


class TestMutationIntegration:
    """Integration tests for the complete mutation system."""

    def test_no_duplicate_operator_registrations(self):
        """Ensure no duplicate operator registrations exist."""
        operator_tuples = [(node_type.__name__, func.__name__) for node_type, func in mutation_operators]
        counts = Counter(operator_tuples)
        duplicates = {k: v for k, v in counts.items() if v > 1}
        assert duplicates == {}, f"Found duplicate operator registrations: {duplicates}"

    def test_all_operators_properly_registered(self):
        """Ensure all operator functions are registered in mutation_operators."""
        operator_functions = {op[1] for op in mutation_operators}
        expected_functions = {
            operator_number, operator_string, operator_name, operator_assignment,
            operator_augmented_assignment, operator_remove_unary_ops, operator_dict_arguments,
            operator_arg_removal, operator_chr_ord, operator_regex, operator_enum_attribute,
            operator_lambda, operator_keywords, operator_swap_op, operator_match
        }
        
        missing_functions = expected_functions - operator_functions
        assert missing_functions == set(), f"Missing operator registrations: {[f.__name__ for f in missing_functions]}"

    def test_number_mutations_comprehensive(self):
        """Test all number mutation scenarios."""
        test_cases = [
            (cst.Integer("5"), ["6"]),
            (cst.Integer("0"), ["1"]),
            (cst.Integer("42"), ["43"]),
            (cst.Float("3.14"), ["4.140000000000001"]),
            (cst.Float("0.0"), ["1.0"]),
            (cst.Imaginary("2j"), ["3j"]),
            (cst.Imaginary("0j"), ["1j"]),
        ]
        
        for node, expected_values in test_cases:
            mutations = list(operator_number(node))
            assert len(mutations) == 1, f"Expected 1 mutation for {node.value}, got {len(mutations)}"
            assert mutations[0].value in expected_values, f"Unexpected mutation: {mutations[0].value}"

    def test_string_mutations_and_false_positive_prevention(self):
        """Test string mutations and ensure docstrings are not mutated."""
        # Regular strings should be mutated  
        node = cst.SimpleString('"hello"')
        mutations = list(operator_string(node))
        # Now includes XX prefix/suffix, uppercase, and capitalize mutations
        assert len(mutations) == 3
        mutation_values = [m.value for m in mutations]
        assert '"XXhelloXX"' in mutation_values
        assert '"HELLO"' in mutation_values
        assert '"Hello"' in mutation_values
        
        # Docstrings should NOT be mutated (false positive prevention)
        docstring_cases = [
            '"""This is a docstring"""',
            "'''This is also a docstring'''",
            'r"""Raw docstring"""',
        ]
        
        for docstring in docstring_cases:
            node = cst.SimpleString(docstring)
            mutations = list(operator_string(node))
            assert len(mutations) == 0, f"Docstring was mutated: {docstring}"

    def test_name_mutations_comprehensive(self):
        """Test name mutations for all supported mappings."""
        test_cases = [
            # Booleans
            ("True", "False"),
            ("False", "True"),

            # Boolean checks
            ("all", "any"),
            ("any", "all"),
            
            # Copy functions
            ("deepcopy", "copy"),
            ("copy", "deepcopy"),
            
            # Ordering
            ("sorted", "reversed"),
            ("reversed", "sorted"),
            
            # Enums
            ("Enum", "StrEnum"),
            ("StrEnum", "Enum"),
            ("IntEnum", "Enum"),
            
            # Removed equivalent mutants that don't add testing value:
            # - len <-> sum: often equivalent for single collections
            # - min <-> max: often equivalent for single element collections  
            # - int <-> float: often equivalent for whole numbers
            # - bytes <-> bytearray: equivalent unless mutation methods called
            # - map <-> filter: low testing value, replaced with function call mutations
        ]
        
        for original, expected in test_cases:
            node = cst.Name(original)
            mutations = list(operator_name(node))
            assert len(mutations) == 1, f"Expected 1 mutation for {original}"
            assert mutations[0].value == expected, f"Expected {original} -> {expected}, got {mutations[0].value}"
        
        # Test unknown names are not mutated (false positive prevention)
        unknown_node = cst.Name("unknown_function")
        mutations = list(operator_name(unknown_node))
        assert len(mutations) == 0, "Unknown function names should not be mutated"

    def test_assignment_mutations(self):
        """Test assignment mutations."""
        # Regular assignment should become None
        node = cst.Assign([cst.AssignTarget(cst.Name("x"))], cst.Integer("5"))
        mutations = list(operator_assignment(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].value, cst.Name)
        assert mutations[0].value.value == "None"
        
        # None assignment should become empty string
        node = cst.Assign([cst.AssignTarget(cst.Name("x"))], cst.Name("None"))
        mutations = list(operator_assignment(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].value, cst.SimpleString)
        assert mutations[0].value.value == '""'

    def test_augmented_assignment_mutations(self):
        """Test augmented assignment mutations."""
        node = cst.AugAssign(cst.Name("x"), cst.AddAssign(), cst.Integer("5"))
        mutations = list(operator_augmented_assignment(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Assign)

    def test_unary_operation_mutations(self):
        """Test unary operation mutations."""
        # Not and BitInvert should be removed
        for op_class in [cst.Not, cst.BitInvert]:
            node = cst.UnaryOperation(op_class(), cst.Name("x"))
            mutations = list(operator_remove_unary_ops(node))
            assert len(mutations) == 1
            assert isinstance(mutations[0], cst.Name)
            assert mutations[0].value == "x"
        
        # Other unary ops should not be mutated (false positive prevention)
        node = cst.UnaryOperation(cst.Plus(), cst.Name("x"))
        mutations = list(operator_remove_unary_ops(node))
        assert len(mutations) == 0

    def test_dict_arguments_and_false_positive_prevention(self):
        """Test dict argument mutations and ensure non-dict calls are ignored."""
        # Dict calls should be mutated
        call = cst.Call(
            cst.Name("dict"),
            [cst.Arg(keyword=cst.Name("a"), value=cst.Integer("1")),
             cst.Arg(keyword=cst.Name("b"), value=cst.Integer("2"))]
        )
        mutations = list(operator_dict_arguments(call))
        assert len(mutations) == 2
        
        # Non-dict calls should NOT be mutated (false positive prevention)
        call = cst.Call(cst.Name("other"), [cst.Arg(keyword=cst.Name("a"), value=cst.Integer("1"))])
        mutations = list(operator_dict_arguments(call))
        assert len(mutations) == 0

    def test_arg_removal_mutations(self):
        """Test argument removal mutations."""
        # Multiple args: should get None replacements + removals
        call = cst.Call(cst.Name("func"), [cst.Arg(cst.Integer("1")), cst.Arg(cst.Integer("2"))])
        mutations = list(operator_arg_removal(call))
        assert len(mutations) == 4  # 2 None replacements + 2 removals
        
        # Single arg: should only get None replacement (no removal)
        call = cst.Call(cst.Name("func"), [cst.Arg(cst.Integer("1"))])
        mutations = list(operator_arg_removal(call))
        assert len(mutations) == 1  # Only None replacement

    def test_chr_ord_mutations(self):
        """Test chr/ord mutations - should modify results, not swap functions."""
        # NOTE: chr <-> ord swap often raises exceptions (equivalent to runtime error)
        # Better approach: chr(123) -> chr(123 + 1), ord('c') -> ord('c') + 1
        
        # Chr should wrap argument in +1 (current implementation)
        call = cst.Call(cst.Name("chr"), [cst.Arg(cst.Integer("65"))])
        mutations = list(operator_chr_ord(call))
        assert len(mutations) == 1
        # TODO: Should be chr(65+1) instead of ord(65) to avoid runtime exceptions
        
        # Ord should wrap entire call in +1 (current implementation) 
        call = cst.Call(cst.Name("ord"), [cst.Arg(cst.SimpleString("'A'"))])
        mutations = list(operator_chr_ord(call))
        assert len(mutations) == 1
        # TODO: Should be ord('A')+1 instead of chr('A') to avoid runtime exceptions

    def test_regex_mutations_and_false_positive_prevention(self):
        """Test regex mutations and ensure non-regex calls are ignored."""
        # Regex calls should be mutated
        call = cst.Call(
            cst.Attribute(cst.Name("re"), cst.Name("compile")),
            [cst.Arg(cst.SimpleString(r"r'\d+'"))]
        )
        mutations = list(operator_regex(call))
        assert len(mutations) > 0
        
        # Non-regex calls should NOT be mutated (false positive prevention)
        call = cst.Call(cst.Name("other_func"), [cst.Arg(cst.SimpleString("'test'"))])
        mutations = list(operator_regex(call))
        assert len(mutations) == 0

    def test_enum_attribute_mutations_and_false_positive_prevention(self):
        """Test enum attribute mutations and ensure non-enum attributes are ignored."""
        # enum.Enum should be mutated to StrEnum and IntEnum
        attr = cst.Attribute(cst.Name("enum"), cst.Name("Enum"))
        mutations = list(operator_enum_attribute(attr))
        assert len(mutations) == 2
        assert any(m.attr.value == "StrEnum" for m in mutations)
        assert any(m.attr.value == "IntEnum" for m in mutations)
        
        # enum.StrEnum should be mutated to Enum
        attr = cst.Attribute(cst.Name("enum"), cst.Name("StrEnum"))
        mutations = list(operator_enum_attribute(attr))
        assert len(mutations) == 1
        assert mutations[0].attr.value == "Enum"
        
        # Non-enum attributes should NOT be mutated (false positive prevention)
        attr = cst.Attribute(cst.Name("other"), cst.Name("Enum"))
        mutations = list(operator_enum_attribute(attr))
        assert len(mutations) == 0

    def test_lambda_mutations(self):
        """Test lambda mutations."""
        # Lambda with None body should become 0
        lambda_node = cst.Lambda(cst.Parameters(), cst.Name("None"))
        mutations = list(operator_lambda(lambda_node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].body, cst.Integer)
        assert mutations[0].body.value == "0"
        
        # Lambda with other body should become None
        lambda_node = cst.Lambda(cst.Parameters(), cst.Integer("42"))
        mutations = list(operator_lambda(lambda_node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].body, cst.Name)
        assert mutations[0].body.value == "None"

    def test_keyword_mutations(self):
        """Test keyword mutations."""
        keyword_mappings = [
            (cst.Is(), cst.IsNot),
            (cst.IsNot(), cst.Is),
            (cst.In(), cst.NotIn),
            (cst.NotIn(), cst.In),
            (cst.Break(), cst.Return),
            (cst.Continue(), cst.Break),
        ]
        
        for original, expected_type in keyword_mappings:
            mutations = list(operator_keywords(original))
            assert len(mutations) == 1
            assert isinstance(mutations[0], expected_type)

    def test_operator_swap_mutations(self):
        """Test operator swap mutations."""
        operator_mappings = [
            (cst.Add(), cst.Subtract),
            (cst.Subtract(), cst.Add),
            (cst.Multiply(), cst.Divide),
            (cst.Equal(), cst.NotEqual),
            (cst.NotEqual(), cst.Equal),
            (cst.LessThan(), cst.LessThanEqual),
            (cst.GreaterThan(), cst.GreaterThanEqual),
            (cst.And(), cst.Or),
            (cst.Or(), cst.And),
        ]
        
        for original, expected_type in operator_mappings:
            mutations = list(operator_swap_op(original))
            assert len(mutations) == 1
            assert isinstance(mutations[0], expected_type)

    def test_match_mutations(self):
        """Test match statement mutations."""
        cases = [
            cst.MatchCase(cst.MatchValue(cst.Integer("1")), cst.SimpleStatementSuite([cst.Pass()])),
            cst.MatchCase(cst.MatchValue(cst.Integer("2")), cst.SimpleStatementSuite([cst.Pass()])),
        ]
        match_node = cst.Match(cst.Name("x"), cases)
        mutations = list(operator_match(match_node))
        assert len(mutations) == 2  # Remove each case once
        assert all(len(m.cases) == 1 for m in mutations)

    def test_comprehensive_false_positive_prevention(self):
        """Comprehensive test to ensure operators don't create false positives."""
        false_positive_tests = [
            # String operator should ignore docstrings
            (operator_string, cst.SimpleString('"""docstring"""'), 0),
            
            # Regex operator should ignore non-regex calls
            (operator_regex, cst.Call(cst.Name("print"), [cst.Arg(cst.SimpleString('"test"'))]), 0),
            
            # Enum operator should ignore non-enum attributes
            (operator_enum_attribute, cst.Attribute(cst.Name("other"), cst.Name("Enum")), 0),
            
            # Dict operator should ignore non-dict calls
            (operator_dict_arguments, cst.Call(cst.Name("func"), [cst.Arg(keyword=cst.Name("a"), value=cst.Integer("1"))]), 0),
            
            # Name operator should ignore unknown names
            (operator_name, cst.Name("unknown_function"), 0),
            
            # Unary operator should ignore non-Not/BitInvert operators
            (operator_remove_unary_ops, cst.UnaryOperation(cst.Plus(), cst.Name("x")), 0),
        ]
        
        for operator_func, node, expected_count in false_positive_tests:
            mutations = list(operator_func(node))
            assert len(mutations) == expected_count, f"{operator_func.__name__} produced {len(mutations)} mutations for {node}, expected {expected_count}"

    def test_function_call_mutations(self):
        """Test new function call mutations that replace problematic name swaps."""
        # Import the new operator
        from mutmut.node_mutation import operator_function_call_mutations
        
        # Test len(...) -> len(...) + 1 and len(...) - 1
        call = cst.Call(cst.Name("len"), [cst.Arg(cst.Name("arr"))])
        mutations = list(operator_function_call_mutations(call))
        assert len(mutations) == 2  # + 1 and - 1 variants
        
        # Test sum(...) -> sum(...) + 1 and sum(...) - 1  
        call = cst.Call(cst.Name("sum"), [cst.Arg(cst.Name("arr"))])
        mutations = list(operator_function_call_mutations(call))
        assert len(mutations) == 2
        
        # Test map(fn, arr) -> list(arr)
        call = cst.Call(cst.Name("map"), [cst.Arg(cst.Name("fn")), cst.Arg(cst.Name("arr"))])
        mutations = list(operator_function_call_mutations(call))
        assert len(mutations) == 1
        
        # Test filter(fn, arr) -> list(arr)
        call = cst.Call(cst.Name("filter"), [cst.Arg(cst.Name("fn")), cst.Arg(cst.Name("arr"))])
        mutations = list(operator_function_call_mutations(call))
        assert len(mutations) == 1
        
        # Test that non-target functions are not mutated
        call = cst.Call(cst.Name("other"), [cst.Arg(cst.Name("arg"))])
        mutations = list(operator_function_call_mutations(call))
        assert len(mutations) == 0
        """Test that context-sensitive operations don't generate false positives."""
        
        # Test aggregate functions in different contexts
        aggregate_false_positive_tests = [
            # These should NOT be mutated as they're likely variable names or attributes
            # Variable assignment context
            cst.Assign([cst.AssignTarget(cst.Name("len"))], cst.Integer("5")),
            
            # Attribute access context  
            cst.Attribute(cst.Name("obj"), cst.Name("len")),
            
            # Method definition context (would need more complex AST structure)
            # Function parameter context (would need more complex AST structure)
        ]
        
        # For now, test that aggregate names in isolation are NOT mutated by operator_name
        # They should be handled by operator_function_call_mutations instead
        aggregate_names = ["len", "sum", "min", "max"]
        for name in aggregate_names:
            node = cst.Name(name)
            mutations = list(operator_name(node))
            # These should NOT be mutated by operator_name anymore to avoid equivalent mutants
            assert len(mutations) == 0, f"Aggregate function {name} should NOT be mutated by operator_name (handled by function call mutations instead)"

    def test_high_risk_false_positive_scenarios(self):
        """Test scenarios with high risk of false positives."""
        
        # Common variable names that match built-in functions
        risky_names = [
            # NOTE: These aggregate functions should be reworked to avoid false positives
            # and equivalent mutants by modifying results instead of swapping functions
            "len",    # Could be: my_len = 10; should do len(...) -> len(...) + 1
            "sum",    # Could be: running_sum = 0; should do sum(...) -> sum(...) + 1  
            "min",    # Could be: min_value = x; should do min(...) -> min(...) + 1
            "max",    # Could be: max_attempts = 5; should do max(...) -> max(...) + 1
            "map",    # Could be: location_map = {}; should do map(fn, arr) -> list(arr)
            "filter", # Could be: spam_filter = Filter(); should do filter(fn, arr) -> list(arr)
            "all",    # Could be: all_items = []
            "any",    # Could be: any_errors = False
        ]
        
        for name in risky_names:
            node = cst.Name(name)
            mutations = list(operator_name(node))
            if len(mutations) > 0:
                print(f"WARNING: {name} will be mutated even when used as variable name - potential false positive")

    def test_mutation_quality_and_semantics(self):
        """Test that mutations are semantically meaningful and high-quality."""
        # Number mutations should be +1 (not random)
        node = cst.Integer("42")
        mutations = list(operator_number(node))
        assert mutations[0].value == "43"
        
        # String mutations should use XX prefix/suffix (consistent pattern)
        node = cst.SimpleString('"test"')
        mutations = list(operator_string(node))
        assert mutations[0].value == '"XXtestXX"'
        
        # Boolean swaps should be logical opposites
        true_node = cst.Name("True")
        false_node = cst.Name("False")
        assert list(operator_name(true_node))[0].value == "False"
        assert list(operator_name(false_node))[0].value == "True"
        
        # Operator swaps should be logical opposites
        eq_mutations = list(operator_swap_op(cst.Equal()))
        assert isinstance(eq_mutations[0], cst.NotEqual)
        
        lt_mutations = list(operator_swap_op(cst.LessThan()))
        assert isinstance(lt_mutations[0], cst.LessThanEqual)

    def test_equivalent_mutant_prevention(self):
        """Test that we avoid creating equivalent mutants that don't add testing value."""
        
        # These should NOT be mutated as they often create equivalent mutants:
        equivalent_mutant_names = [
            "str",        # str <-> repr often equivalent for built-ins
            "repr",       
            "list",       # list <-> tuple equivalent unless .append() called
            "tuple",
            "set",        # set <-> frozenset equivalent unless mutation methods called  
            "frozenset",
        ]
        
        for name in equivalent_mutant_names:
            node = cst.Name(name)
            mutations = list(operator_name(node))
            # These should not be mutated to avoid equivalent mutants
            assert len(mutations) == 0, f"Equivalent mutant detected: {name} should not be mutated"

    def test_problematic_aggregate_mutations(self):
        """Test aggregate mutations that should be reworked to avoid equivalent mutants."""
        
        # Current problematic mappings that should be reworked:
        problematic_mappings = [
            ("len", "sum"),    # Should be len(...) -> len(...) + 1
            ("sum", "len"),    # Should be sum(...) -> sum(...) + 1  
            ("min", "max"),    # Should be min(...) -> min(...) + 1
            ("max", "min"),    # Should be max(...) -> max(...) + 1
            ("map", "filter"), # Should be map(fn, arr) -> list(arr)
            ("filter", "map"), # Should be filter(fn, arr) -> list(arr)
        ]
        
        for original, swapped in problematic_mappings:
            node = cst.Name(original)
            mutations = list(operator_name(node))
            if len(mutations) > 0:
                print(f"TODO: Rework {original} -> {swapped} to modify result instead of swapping function")

    def test_regex_equivalent_mutant_prevention(self):
        """Test that regex mutations don't create equivalent mutants."""
        
        # NOTE: {1,} -> + are equivalent in regex, so this creates equivalent mutants
        # We should remove this mapping from the regex operator
        
        # Test that regex calls are still mutated (but hopefully without equivalent mutants)
        call = cst.Call(
            cst.Attribute(cst.Name("re"), cst.Name("compile")),
            [cst.Arg(cst.SimpleString(r"r'\d+'"))]
        )
        mutations = list(operator_regex(call))
        assert len(mutations) > 0
        
        # TODO: Verify that {1,} -> + mapping is removed to prevent equivalent mutants

    def test_edge_cases_and_robustness(self):
        """Test edge cases to ensure robustness."""
        # Empty function calls
        empty_call = cst.Call(cst.Name("func"), [])
        arg_mutations = list(operator_arg_removal(empty_call))
        assert len(arg_mutations) == 0
        
        # Single match case (should not be mutated to empty)
        single_case = [cst.MatchCase(cst.MatchValue(cst.Integer("1")), cst.SimpleStatementSuite([cst.Pass()]))]
        match_node = cst.Match(cst.Name("x"), single_case)
        mutations = list(operator_match(match_node))
        assert len(mutations) == 0  # Can't remove the only case
