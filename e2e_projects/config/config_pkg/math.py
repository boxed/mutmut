def add(a, b):
    return a + b

def call_depth_two():
    return call_depth_three() - 1

def call_depth_three():
    return call_depth_four() - 1

def call_depth_four():
    return call_depth_five() - 1

def call_depth_five():
    return 5