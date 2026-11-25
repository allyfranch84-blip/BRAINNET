"""Legacy entrypoint retired: the Kernel is the only inference supervisor.

Do not start a competing watchdog or kill processes on an HTTP timeout.
"""
if __name__ == '__main__':
    print('Watchdog legado desativado. Use iniciar_aios.bat; o Kernel supervisiona a inferencia.')
