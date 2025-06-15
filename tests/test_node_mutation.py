import libcst as cst
from mutmut.node_mutation import (
    operator_number, operator_string, operator_name, operator_assignment,
    operator_augmented_assignment, operator_remove_unary_ops, operator_dict_arguments,
    operator_arg_removal, operator_chr_ord, operator_regex, operator_enum_attribute,
    operator_lambda, operator_keywords, operator_swap_op, operator_match
)


class TestOperatorNumber:
    def test_integer_mutation(self):
        node = cst.Integer("5")
        mutations = list(operator_number(node))
        assert len(mutations) == 1
        assert mutations[0].value == "6"
    
    def test_float_mutation(self):
        node = cst.Float("3.14")
        mutations = list(operator_number(node))
        assert len(mutations) == 1
        assert mutations[0].value == "4.140000000000001"
    
    def test_imaginary_mutation(self):
        node = cst.Imaginary("2j")
        mutations = list(operator_number(node))
        assert len(mutations) == 1
        assert mutations[0].value == "3j"


class TestOperatorString:
    def test_simple_string_mutation(self):
        node = cst.SimpleString('"hello"')
        mutations = list(operator_string(node))
        # Now includes XX prefix/suffix, uppercase, and capitalize mutations
        assert len(mutations) == 3
        mutation_values = [m.value for m in mutations]
        assert '"XXhelloXX"' in mutation_values
        assert '"HELLO"' in mutation_values  
        assert '"Hello"' in mutation_values
    
    def test_triple_quoted_string_ignored(self):
        node = cst.SimpleString('"""docstring"""')
        mutations = list(operator_string(node))
        assert len(mutations) == 0


class TestOperatorName:
    def test_boolean_swap(self):
        node = cst.Name("True")
        mutations = list(operator_name(node))
        assert len(mutations) == 1
        assert mutations[0].value == "False"
    
    def test_aggregate_function_no_longer_swapped(self):
        # len is no longer swapped to sum (equivalent mutant removed)
        node = cst.Name("len")
        mutations = list(operator_name(node))
        assert len(mutations) == 0  # No longer mutated by operator_name
    
    def test_unknown_name_no_mutation(self):
        node = cst.Name("unknown_function")
        mutations = list(operator_name(node))
        assert len(mutations) == 0


class TestOperatorAssignment:
    def test_assign_to_none(self):
        node = cst.Assign([cst.AssignTarget(cst.Name("x"))], cst.Integer("5"))
        mutations = list(operator_assignment(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].value, cst.Name)
        assert mutations[0].value.value == "None"
    
    def test_none_to_empty_string(self):
        node = cst.Assign([cst.AssignTarget(cst.Name("x"))], cst.Name("None"))
        mutations = list(operator_assignment(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].value, cst.SimpleString)
        assert mutations[0].value.value == '""'


class TestOperatorAugmentedAssignment:
    def test_add_assign_to_assign(self):
        node = cst.AugAssign(cst.Name("x"), cst.AddAssign(), cst.Integer("5"))
        mutations = list(operator_augmented_assignment(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Assign)
        assert len(mutations[0].targets) == 1
        assert mutations[0].targets[0].target.value == "x"
        assert mutations[0].value.value == "5"


class TestOperatorDictArguments:
    def test_dict_keyword_mutation(self):
        call = cst.Call(
            cst.Name("dict"),
            [cst.Arg(keyword=cst.Name("a"), value=cst.Integer("1")),
             cst.Arg(keyword=cst.Name("b"), value=cst.Integer("2"))]
        )
        mutations = list(operator_dict_arguments(call))
        assert len(mutations) == 2
        # Check that keywords are mutated to have XX suffix
        assert any(arg.keyword.value == "aXX" for m in mutations for arg in m.args)
        assert any(arg.keyword.value == "bXX" for m in mutations for arg in m.args)
    
    def test_non_dict_call_ignored(self):
        call = cst.Call(cst.Name("other"), [cst.Arg(keyword=cst.Name("a"), value=cst.Integer("1"))])
        mutations = list(operator_dict_arguments(call))
        assert len(mutations) == 0


class TestOperatorRemoveUnaryOps:
    def test_not_removal(self):
        node = cst.UnaryOperation(cst.Not(), cst.Name("x"))
        mutations = list(operator_remove_unary_ops(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Name)
        assert mutations[0].value == "x"
    
    def test_bit_invert_removal(self):
        node = cst.UnaryOperation(cst.BitInvert(), cst.Name("x"))
        mutations = list(operator_remove_unary_ops(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Name)
        assert mutations[0].value == "x"
    
    def test_other_unary_ops_ignored(self):
        node = cst.UnaryOperation(cst.Plus(), cst.Name("x"))
        mutations = list(operator_remove_unary_ops(node))
        assert len(mutations) == 0


class TestOperatorKeywords:
    def test_is_to_is_not(self):
        node = cst.Is()
        mutations = list(operator_keywords(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.IsNot)
    
    def test_in_to_not_in(self):
        node = cst.In()
        mutations = list(operator_keywords(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.NotIn)
    
    def test_break_to_return(self):
        node = cst.Break()
        mutations = list(operator_keywords(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Return)
    
    def test_continue_to_break(self):
        node = cst.Continue()
        mutations = list(operator_keywords(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Break)


class TestOperatorArgRemoval:
    def test_replace_arg_with_none(self):
        call = cst.Call(cst.Name("func"), [cst.Arg(cst.Integer("1")), cst.Arg(cst.Integer("2"))])
        mutations = list(operator_arg_removal(call))
        assert len(mutations) == 4  # 2 None replacements + 2 removals
    
    def test_single_arg_removal(self):
        call = cst.Call(cst.Name("func"), [cst.Arg(cst.Integer("1"))])
        mutations = list(operator_arg_removal(call))
        assert len(mutations) == 1  # Only None replacement, no removal for single arg


class TestOperatorChrOrd:
    def test_chr_mutation(self):
        call = cst.Call(cst.Name("chr"), [cst.Arg(cst.Integer("65"))])
        mutations = list(operator_chr_ord(call))
        assert len(mutations) == 1
        # Should wrap the argument in a BinaryOperation adding 1
    
    def test_ord_mutation(self):
        call = cst.Call(cst.Name("ord"), [cst.Arg(cst.SimpleString("'A'"))])
        mutations = list(operator_chr_ord(call))
        assert len(mutations) == 1
        # Should wrap the entire call in a BinaryOperation adding 1


class TestOperatorRegex:
    def test_regex_compile_mutation(self):
        call = cst.Call(
            cst.Attribute(cst.Name("re"), cst.Name("compile")),
            [cst.Arg(cst.SimpleString(r"r'\d+'"))]
        )
        mutations = list(operator_regex(call))
        assert len(mutations) > 0  # Should generate multiple regex mutations
    
    def test_non_regex_call_ignored(self):
        call = cst.Call(cst.Name("other_func"), [cst.Arg(cst.SimpleString("'test'"))])
        mutations = list(operator_regex(call))
        assert len(mutations) == 0


class TestOperatorEnumAttribute:
    def test_enum_to_strenum(self):
        attr = cst.Attribute(cst.Name("enum"), cst.Name("Enum"))
        mutations = list(operator_enum_attribute(attr))
        assert len(mutations) == 2
        assert any(m.attr.value == "StrEnum" for m in mutations)
        assert any(m.attr.value == "IntEnum" for m in mutations)
    
    def test_strenum_to_enum(self):
        attr = cst.Attribute(cst.Name("enum"), cst.Name("StrEnum"))
        mutations = list(operator_enum_attribute(attr))
        assert len(mutations) == 1
        assert mutations[0].attr.value == "Enum"


class TestOperatorLambda:
    def test_lambda_none_to_zero(self):
        lambda_node = cst.Lambda(cst.Parameters(), cst.Name("None"))
        mutations = list(operator_lambda(lambda_node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].body, cst.Integer)
        assert mutations[0].body.value == "0"
    
    def test_lambda_other_to_none(self):
        lambda_node = cst.Lambda(cst.Parameters(), cst.Integer("42"))
        mutations = list(operator_lambda(lambda_node))
        assert len(mutations) == 1
        assert isinstance(mutations[0].body, cst.Name)
        assert mutations[0].body.value == "None"


class TestOperatorSwapOp:
    def test_addition_to_subtraction(self):
        node = cst.Add()
        mutations = list(operator_swap_op(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.Subtract)
    
    def test_equality_swap(self):
        node = cst.Equal()
        mutations = list(operator_swap_op(node))
        assert len(mutations) == 1
        assert isinstance(mutations[0], cst.NotEqual)


class TestOperatorMatch:
    def test_match_case_removal(self):
        cases = [
            cst.MatchCase(cst.MatchValue(cst.Integer("1")), cst.SimpleStatementSuite([cst.Pass()])),
            cst.MatchCase(cst.MatchValue(cst.Integer("2")), cst.SimpleStatementSuite([cst.Pass()])),
        ]
        match_node = cst.Match(cst.Name("x"), cases)
        mutations = list(operator_match(match_node))
        assert len(mutations) == 2  # Remove each case once
        assert all(len(m.cases) == 1 for m in mutations)


class TestIntegration:
    def test_all_operators_registered(self):
        """Ensure all operators are properly registered in mutation_operators"""
        from mutmut.node_mutation import mutation_operators
        
        operator_functions = {op[1] for op in mutation_operators}
        expected_functions = {
            operator_number, operator_string, operator_name, operator_assignment,
            operator_augmented_assignment, operator_remove_unary_ops, operator_dict_arguments,
            operator_arg_removal, operator_chr_ord, operator_regex, operator_enum_attribute,
            operator_lambda, operator_keywords, operator_swap_op, operator_match
        }
        
        assert operator_functions >= expected_functions
