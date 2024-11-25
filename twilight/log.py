from clock import clock


class Log:
    def __init__(self):
        self.in_gossip = False

    @staticmethod
    def timestamp():
        if clock.is_valid():
            return clock.now().astimezone().strftime('%Y/%m/%d %H:%M:%S')
        else:
            return '----/--/-- --:--:--'

    def print(self, *args, **kwargs):
        if self.in_gossip:
            print()
            self.in_gossip = False

        print(f'[{self.timestamp()}]', *args, **kwargs)

    def print_gossip(self, *args, **kwargs):
        if not self.in_gossip:
            print(f'[{self.timestamp()}] gossip:', *args, **kwargs, end=' ')
            self.in_gossip = True

        print(*args, **kwargs, end=' ', flush=True)


log = Log()
