import csv
from email.utils import getaddresses
import numpy as np


def decompress_time(time: int) -> tuple[int, int, int]:
    """Extract time from word"""
    second = (time % 30) *2
    minute = (time // 30) % 60
    hour = time // 1800
    # print(f"{hour}:{min}:{sec}")
    return hour, minute, second


def decompress_date(date: int) -> tuple[int, int, int]:
    """Extract date from word"""
    day = date & 0x001F
    month = (date >> 5) & 0x000F
    year = (date >> 9) & 0x007F
    # print(f'{day}/{month}/{year+2000}')
    return day, month, year


def parse_bytes(byte: bytes) -> int:
    """Parse 2's complement word encoded in little endian into int"""
    return int.from_bytes(byte, byteorder='little', signed=True)


# .svn file headers
HEADERS = {
    0x01: 'file header',
    0x02: 'unit header',
    0x03: 'user text',
    0x04: 'global settings',
    0x05: 'channel settings (hardware)',
    0x31: 'trigger event settings',
    0x07: 'channel settings (software)',
    0x08: 'profile settings',
    0x1E: 'vector settings',
    0x18: 'buffer header',
    0x09: 'octaves settings',
    0x0A: 'octaves settings in channels',
    0x34: 'cross spectrum settings',
    0x21: 'spectrum buffer header',
    0x0D: 'main results',
    0x0E: 'slm/vlm results',
    0x19: 'statistical levels',
    0x10: 'octave results',
    0x39: 'octave results (peak)'
}

# Headers which contain other headers inside
CONTAINERS = [7, 9, 14]

# Specific frequencies in the buffer [Hz]
FREQUENCIES = (
    0.8, 1, 1.25, 1.6, 2, 2.5, 3.15, 4, 5, 6.3,
    8, 10, 12.5, 16, 20, 25, 31.5, 40, 50, 63,
    80, 100, 125, 160, 200, 250, 315, 400, 500, 630,
    800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300,
    8000, 10000, 12500, 16000, 20000
)
# FREQUENCIES[18:-6] -> 50Hz : 5000Hz
# FREQUENCIES[18:39] -> 50Hz : 5000Hz


class svn_buffer_parser():
    def __init__(self) -> None:
        self.data = None
        self.channels = 3
        self.samples = 160
        self.frequencies = len(FREQUENCIES)
        self.totals = 3 # A, C, Lin
        self.step = 100 # ms
        
        self.file = ''
        self.buffer_file = ''


    def load(self, path: str) -> bool:
        """Load and parse main file or buffer file.

        Parameters:\n
        path -- file to open

        Returns:
        True -- read was succesfull
        False -- read was not succesfull
        """

        file = open(path, 'rb')
        file.read(32) # SVN file header

        # Read all of the headers
        while True:
            # Start with reading header number and header length
            header = int.from_bytes(file.read(1), byteorder='little')
            length = int.from_bytes(file.read(1), byteorder='little')
            
            if header in CONTAINERS:
                file.read(2)
                continue

            # If length equals 0, actual length is stored in next word
            if length == 0:
                length = int.from_bytes(file.read(2), byteorder='little') - 1
            
            # ==================== Headers that will actually be read ===================
            # Every header here needs to end with continue

            # File header

            # Buffer header
            if header == 0x18:
                file.read(4) # First 2 words can be omited
                self.step = parse_bytes(file.read(2)) # Time step between measurements
                file.read(4) # Next word can be omited
                
                self.samples = parse_bytes(file.read(4)) # Number of measurements (long)

                # Skip the rest
                file.read(2 * (length - 8))
                continue

            # =========================== End of read headers ===========================
            
            # Skip the contents of every other header
            file.read(2 * (length - 1))
            
            # Buffer contents
            if header == 0x21:
                self.read_buffer_contents(file)
                break

            # Main results
            if header == 0x19:
                self.read_main_contents(file)
                break
        
        if file.read(2) == b'\xff\xff':
            return True
        return False


    def read_buffer_contents(self, file) -> None:
        # Read buffer contents
        self.channels = 3
        # self.samples = 160
        # self.frequencies = len(FREQUENCIES)
        self.totals = 3 # A, C, Lin

        # Preallocate arrays for buffer contents
        self.data = [[[0 for _ in range(self.samples)] 
            for _ in range(self.frequencies + self.totals)] 
            for _ in range(self.channels)]

        self.leq = [[0 for _ in range(self.samples)] 
            for _ in range(self.channels)]

        for sample in range(self.samples):
            # Channels 1,2,3... in a row
            for channel in range(3):
                num = parse_bytes(file.read(2)) / 20

                # Add to output array
                self.leq[channel][sample] = num

            # Channel 1 tercets and totals, channel 2 tercets and totals...
            for channel in range(self.channels):

                # First word is always 0000h
                if parse_bytes(file.read(2)) != 0:
                    print('ERROR')

                # Tercets followed by totals
                for value in range(self.frequencies + self.totals):
                    num = parse_bytes(file.read(2)) / 10
                    
                    # Add to output array
                    self.data[channel][value][sample] = num


    def read_main_contents(self, file):
        self.data = [ [] for _ in range(self.channels) ]

        for channel in range(self.channels * 2):
            # Tercets and peak values
            # Header
            header = int.from_bytes(file.read(1), byteorder='little')

            # Length and first word can be skipped
            file.read(3)

            # Second word is number of tercets
            self.frequencies = parse_bytes(file.read(2))

            # Third word is number of totals
            self.totals = parse_bytes(file.read(2))

            # Tercets followed by totals
            for value in range(self.frequencies + self.totals):
                num = parse_bytes(file.read(2)) / 100

                # Add to output array, skip peaks
                if header == 0x10:
                    self.data[channel // 2].append(num)


    def get_data(self, channel):
        """Returns list with data containing frequencies from 50Hz to 5kHz and totals.
        """
        return (self.data[channel][18:39][:] + self.data[channel][-3:][:]).copy()


    def export_csv(self, path: str = 'output') -> None:
        """Export data to csv files in specified directory.

        Parameters:\n
        path -- directory for exported files (default 'output')
        """

        for i in range(self.channels):
            with open(f'{path}/main{i}.csv', 'w', newline='') as out_file:
                csv_writer = csv.writer(out_file)
                csv_writer.writerows(self.data[i, 0:1, :])

            with open(f'{path}/tercets{i}.csv', 'w', newline='') as out_file:
                csv_writer = csv.writer(out_file)
                csv_writer.writerows(self.data[i, 1:-self.totals, :])

            with open(f'{path}/totals{i}.csv', 'w', newline='') as out_file:
                csv_writer = csv.writer(out_file)
                csv_writer.writerows(self.data[i, -self.totals:, :])


def main():
    reader = svn_buffer_parser()
    print('Loading Buffer file')
    reader.load('PBL_Badania_v1/Buffe_11.svn')
    print(reader.get_data(0)[1:3:1][1])
    # reader.export_csv('out')
    print('Loading Main file')
    reader.load('PBL_Badania_v1/@PBL10.svn')
    print(reader.get_data(0)[-4])


if __name__ == '__main__':
    main()