from statistics import mean
from math import log10
from svnparser import svn_parser


def log_mean(files, channel):
    """Returns logarithmic mean for each frequency in given files

    Args:
        files (list): list of main file paths to extract data from
        channel (int): returns data from this channel, starts from 0

    Returns:
        list: logarithmic mean
    """
    reader = svn_parser()

    # Load data from main svn files
    data = []
    for file in files:
        reader.load(file)
        data.append(reader.get_data(channel))

    # Calculate powers to later use in logarithms
    for file in range(len(data)):
        for sample in range(len(data[0])):
            data[file][sample] = 10 ** (data[file][sample] / 10)

    # Calculate arithmetic mean
    data_mean = [0 for _ in range(len(data[0]))]
    for sample in range(len(data[0])):
        data_mean[sample] = mean([row[sample] for row in data])

    # Calculate logarithms and return result
    return [10*log10(n) for n in data_mean]


def main():
    files = [f"../svn parser/PBL_Badania_v1/@PBL{n}.svn" for n in range(6,12)]
    print("@PBL6 - @PBL11, channel 1")
    print(log_mean(files, 0))
    print("@PBL6 - @PBL11, channel 2")
    print(log_mean(files, 1))


if __name__ == '__main__':
    main()