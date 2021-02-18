import micropython
micropython.opt_level(2)

import sys
import uos
import uio
import pyb
import gc

def log_exception(exc, time_str = "", to_print = True, to_file = False, fatal = False, reboot = False):

    s = ""
    # use built-in exception formatter
    if exc is not None:
        if "str" not in str(type(exc)):
            s = exc_to_str(exc)
    gc.collect()

    # use sys time if real time is not provided
    if time_str is None:
        time_str = ""
    if len(time_str) <= 0:
        time_str = "%u" % pyb.millis()

    if exc is not None:
        if "str" not in str(type(exc)):
            headstr = "ERROR[%s]: %s" % (time_str, str(type(exc)))
            # traceback made single line
            s = s.replace("\n  ", " >> ")
        else:
            headstr = "MESSAGE[%s]: %s" % (time_str, exc)
    else:
        headstr = "UNKNOWN-EVENT[%s]" % time_str

    if to_print:
        print(headstr)
        print(s)
    if to_file:
        # append to this file
        fname = "error_log.txt"
        fsize = 0
        retries = 0
        while retries < 2:
            retries += 1
            try:
                try:
                    fsize = uos.stat(fname)[6]
                except OSError:
                    # no such file, file size is 0 (unchanged)
                    pass
                with open(fname, "wba+") as f:
                    f.seek(fsize) # the append flag does not work in micropython
                    f.write("\r\n")
                    f.write(headstr + "\r\n")
                    f.write(s + "\r\n")
                    f.write("\r\n")
                break # done, no need to loop
            except:
                # something wrong happened
                # backup the old file, start a new one
                backup_old()
                continue
    if reboot:
        import machine
        machine.reset()
    if fatal or "IDE interrupt" in s:
        raise exc
    return headstr + "\r\n" + s

def exc_to_str(exc):
    with uio.StringIO(512) as f:
        sys.print_exception(exc, f)
        f.seek(0)
        return f.read()

def backup_old():
    try:
        nfn = "error_log_old.txt"
        try:
            uos.remove(nfn)
        except OSError:
            pass
        uos.rename("error_log.txt", nfn)
        return True
    except OSError:
        pass
    return False

def init():
    try:
        fname = "error_log.txt"
        fsize = uos.stat(fname)[6]
        if fsize > (1024 * 1024):
            backup_old()
    except OSError:
        pass

"""
def testnest():
    f = open("2")

def test():
    try:
        testnest()
    except Exception as exc:
        log_exception(exc, fatal = True)
        print("done\n\n")

if __name__ == "__main__":
    test()
"""
