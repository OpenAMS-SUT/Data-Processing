import csv


def decompress_time(time: int) -> tuple[int, int, int]:
    """Extract time from word
    
    Args:
        time (int): 16 bit integer to decode into time

    Returns:
        hour (int): decoded hour
        minute (int): decoded minute
        second (int): decoded second
    """
    second = (time % 30) * 2
    minute = (time // 30) % 60
    hour = time // 1800
    # print(f"{hour}:{min}:{sec}")
    return hour, minute, second


def decompress_date(date: int) -> tuple[int, int, int]:
    """Extract date from word
    
    Args:
        date (int): 16 bit integer to decode into date

    Returns:
        hour (int): decoded day
        month (int): decoded month
        year (int): decoded year
    """
    day = date & 0x001F
    month = (date >> 5) & 0x000F
    year = (date >> 9) & 0x007F
    return day, month, year + 2000


def parse_bytes(byte: bytes) -> int:
    """Parse 2's complement bytes encoded in little endian into int"""
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
    "0.8Hz", "1Hz", "1.25Hz", "1.6Hz", "2Hz", "2.5Hz", "3.15Hz", "4Hz", "5Hz", "6.3Hz",
    "8Hz", "10Hz", "12.5Hz", "16Hz", "20Hz", "25Hz", "31.5Hz", "40Hz", "50Hz", "63Hz",
    "80Hz", "100Hz", "125Hz", "160Hz", "200Hz", "250Hz", "315Hz", "400Hz", "500Hz", "630Hz",
    "800Hz", "1000Hz", "1250Hz", "1600Hz", "2000Hz", "2500Hz", "3150Hz", "4000Hz", "5000Hz", "6300Hz",
    "8000Hz", "10000Hz", "12500Hz", "16000Hz", "20000Hz"
)
# FREQUENCIES[18:-6] -> 50Hz : 5000Hz
# FREQUENCIES[18:39] -> 50Hz : 5000Hz


class svn_parser():
    """Class for parsing main and buffer svn files

    Example:
        >>> r = svn_parser()
        >>> r.load('PBL_Badania_v1/@PBL10.svn')
        True
        >>> r.time
        (17, 22, 0)
        >>> r.get_data(0)[:5]
        [88.52, 84.97, 99.19, 97.88, 99.5]

    Note:
        Class atttributes become available after loading appropriate file.

    Attributes:
        file (str): name of the loaded file
        associated_file (str): name of the file associated with the loaded one
        date (tuple): measurement date 
        time (tuple): measurement time
        data (list): entire data from main file, used for acoustic level calculations
        sampled_data (list): entire buffer data, used in reverberation time calculations
    """

    def __init__(self) -> None:
        self.data = None
        self.sampled_data = None
        self.leq = None

        self.channels = 3
        self.samples = 160
        self.frequencies = len(FREQUENCIES)
        self.totals = 3 # A, C, Lin
        self.step = 100 # ms
        
        self.file = ''
        self.associated_file = ''
        self.date = None
        self.time = None


    def load(self, path: str) -> bool:
        """Load and parse main file or buffer file.

        Args:
            path (str): file to open

        Returns:
            bool: True if the load was success, False otherwise.
        """

        file = open(path, 'rb')
        file.read(32) # SVN file header

        # Read all of the headers
        while True:
            # Start with reading header number and header length
            header = int.from_bytes(file.read(1), byteorder='little')
            length = int.from_bytes(file.read(1), byteorder='little')
            
            # If the header only specifies more headers inside it, skip it
            if header in CONTAINERS:
                file.read(2)
                continue

            # If length equals 0, actual length is stored in next word
            if length == 0:
                length = int.from_bytes(file.read(2), byteorder='little') - 1
            
            # ==================== Headers that will actually be read ===================
            # Every header here needs to end with continue

            # File header
            if header == 0x01:
                self.file = file.read(8).decode("utf-16")
                file.read(2)
                self.date = decompress_date(parse_bytes(file.read(2)))
                self.time = decompress_time(parse_bytes(file.read(2)))
                self.associated_file = file.read(8).decode('utf-16')
                continue

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
        
        # Last word is always FFFFh
        if file.read(2) == b'\xff\xff':
            return True
        return False


    def read_main_contents(self, file):
        """Read measurement results from main file

        Note:
            Don't use this function outside.
        """

        # data: value for each individual frequency and total
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
            for _ in range(self.frequencies + self.totals):
                num = parse_bytes(file.read(2)) / 100

                # Add to output array, skip peaks
                if header == 0x10:
                    self.data[channel // 2].append(num)


    def read_buffer_contents(self, file) -> None:
        """Read measurement results from buffer file

        Note:
            Don't use this function outside.
        """
        self.channels = 3
        # self.samples = 160
        # self.frequencies = len(FREQUENCIES)
        self.totals = 3 # A, C, Lin

        # Preallocate arrays for buffer contents
        # sampled_data: individual frequencies and totals
        self.sampled_data = [[[0 for _ in range(self.samples)] 
            for _ in range(self.frequencies + self.totals)] 
            for _ in range(self.channels)]

        # equivalent sound level
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
                    self.sampled_data[channel][value][sample] = num


    def get_data(self, channel):
        """Returns list with data containing frequencies from 50Hz to 5kHz and totals (A, C, Lin)

        Args:
            channel (int): returns data from this channel, starts from 0

        Returns:
            list: copy of frequencies and totals
        """
        return (self.data[channel][18:39] + self.data[channel][-3:]).copy()


    def get_sampled_data(self, channel):
        """Returns list with data samples for frequencies from 50Hz to 5kHz and totals (A, C, Lin)

        Args:
            channel (int): returns data from this channel, starts from 0

        Returns:
            list: copy of frequencies and totals
        """
        return (self.sampled_data[channel][18:39][:] + self.sampled_data[channel][-3:][:]).copy()


    def export_csv(self, path: str = 'output') -> None:
        """Export data to csv files in specified directory

        Note:
            Output folder needs to be created beforehand

        Args:
            path (str): directory for exported files (default 'output')
        """

        description = FREQUENCIES[18:39] + ('Tot A', 'Tot C', 'Tot Lin')
        dlen = len(description)

        for i in range(self.channels):
            if self.data != None:
                with open(f'{path}/main{i}.csv', 'w', newline='') as out_file:
                    csv_writer = csv.writer(out_file)
                    # csv_writer.writerow(self.get_data(i))
                    # Transposition
                    for n, d in enumerate(description):
                        csv_writer.writerow([d] + [self.get_data(i)[n]])

            if self.sampled_data != None:
                with open(f'{path}/buffer{i}.csv', 'w', newline='') as out_file:
                    csv_writer = csv.writer(out_file)
                    # csv_writer.writerows(self.get_sampled_data(i))
                    # Transposition
                    for n, d in enumerate(description):
                        csv_writer.writerow([d] + self.get_sampled_data(i)[n])


def main():
    reader = svn_parser()
    reader.load('PBL_Badania_v1/@PBL10.svn')
    print(reader.time)
    print(reader.get_data(0)[:5])
    reader.export_csv()


if __name__ == '__main__':
    main()