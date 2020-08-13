import micropython
micropython.opt_level(2)

class FakeStream(object):
    def __init__(self):
        pass

    def write(self, s):
        print(s, end="")

    def close(self):
        print("")
