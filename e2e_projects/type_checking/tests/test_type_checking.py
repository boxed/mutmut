from type_checking import *

def test_hello():
    assert hello() == "Hello from type-checking!"

def test_a_hello_wrapper():
    assert isinstance(a_hello_wrapper(), str)

def test_mutate_me():
    assert mutate_me() == "charlie"

def test_color_from_index():
    assert isinstance(Color.from_index(1), Color)

def test_color_to_index():
    assert isinstance(Color.to_index(Color.GREEN), int)

def test_next_color_value():
    assert Color.get_next_color(Color.RED) != Color.RED

def test_create_color():
    assert Color.create('red') == Color.RED

def test_color_to_string():
    assert Color.RED.darken() != Color.RED
