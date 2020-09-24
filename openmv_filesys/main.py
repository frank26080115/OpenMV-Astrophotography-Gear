import polarscope
import exclogger
import pyb

def main():
    pyb.delay(3000)
    scope = polarscope.PolarScope(debug = False)
    while True:
        try:
            scope.task()
        except KeyboardInterrupt:
            raise
        except MemoryError as exc:
            exclogger.log_exception(exc, to_file = False)
            micropython.mem_info(True)
        except Exception as exc:
            exclogger.log_exception(exc)

if __name__ == "__main__":
    main()
