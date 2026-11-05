import os
import pathlib
import re
import stat

from evdev import InputDevice, UInput


class ContainerUInput(UInput):
    def __init__(self, *args, **kwargs):
        self.created_node = None
        super().__init__(*args, **kwargs)
        if self.device is None:
            raise RuntimeError('Could not open the newly allocated virtual touchscreen event node')

    def _find_device_linux(self, sysname):
        if not re.fullmatch(r'input[0-9]+', sysname):
            raise ValueError('Unexpected uinput sysfs name')
        events = list(pathlib.Path('/sys/devices/virtual/input', sysname).glob('event[0-9]*'))
        if len(events) != 1:
            raise ValueError('Expected one event node for the allocated virtual input')
        major, minor = map(int, (events[0] / 'dev').read_text().strip().split(':'))
        if major != 13 or minor < 64:
            raise ValueError('Unexpected virtual evdev device number')
        directory = pathlib.Path('/dev/input')
        directory.mkdir(exist_ok=True)
        node = directory / events[0].name
        number = os.makedev(major, minor)
        if not node.exists():
            os.mknod(node, stat.S_IFCHR | 0o600, number)
            self.created_node = (node, number)
        metadata = node.lstat()
        if not stat.S_ISCHR(metadata.st_mode) or metadata.st_rdev != number:
            raise ValueError('Input node does not match the allocated virtual device')
        return InputDevice(str(node))

    def close(self):
        try:
            super().close()
        finally:
            if self.created_node is not None:
                node, number = self.created_node
                if node.exists() and node.lstat().st_rdev == number:
                    node.unlink()
                self.created_node = None
