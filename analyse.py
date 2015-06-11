#!/usr/bin/env python
# vim: set ai ts=4 sw=4 sts=4 noet fileencoding=utf-8 ft=python

# IMPORTANT!
# Change the paths below according to your needs
INPUT_DATA_PATH = '~/git/simulation_chain/merged'
OUTPUT_DATA_PATH = '~/analysis/output'
GOAT_PATH = '~/git/ClassBasedAnalysis'
GOAT_BUILD = '~/git/ClassBasedAnalysis/qt-build'
GOAT_BIN = 'etap_dalitz'
GOAT_CONFIG = '/dev/null'  # relative path to GOAT_PATH (e. g. "configfiles/GoAT-Analysis.dat") or /dev/null for no config file
INPUT_FILE_PREFIX = 'Goat_merged'
OUTPUT_FILE_PREFIX = 'Analysis'
ROOTSYS = ''#'/opt/root-6.04.00'  # alternative ROOTSYS which should be used instead of the (probably) local defined ROOTSYS environmental variable; leave blank if the usual ROOTSYS should be used, i. e. ROOTSYS = ''

# End of user changes

import os, sys
import re
import errno
import argparse
import logging
import datetime
import subprocess
import fileinput
from shutil import copyfile, move
from os.path import join as pjoin
from math import sqrt, ceil
from copy import copy  # used to make copies of histograms that they won't get deleted after closing the file
# import module which provides colored output
from color import *


logging.setLoggerClass(ColoredLogger)
logger = logging.getLogger('Analysis')
#logger.setLevel(logging.DEBUG)

channels = [
    'etap_e+e-g',
    'etap_pi+pi-eta',
    'etap_rho0g',
    'etap_mu+mu-g',
    'etap_gg',
    'eta_e+e-g',
    'eta_pi+pi-g',
    'eta_pi+pi-pi0',
    'eta_mu+mu-g',
    'eta_gg',
    'omega_e+e-pi0',
    'omega_pi+pi-pi0',
    'omega_pi+pi-',
    'rho0_e+e-',
    'rho0_pi+pi-',
    'pi0_e+e-g',
    'pi0_gg',
    'pi+pi-pi0',
    'pi+pi-',
    'pi0pi0_4g',
    'pi0eta_4g',
    'etap_pi0pi0eta',
    'etap_pi0pi0pi0',
    'etap_pi+pi-pi0',
    'etap_omegag',
    'omega_etag'
]

def check_path(path, create=False, silent=False):
    path = os.path.expanduser(path)
    exist = os.path.isdir(path)
    if not exist and create:
        if not silent:
            print("Directory '%s' does not exist, it will be created now" % path)
        # try to create the directory; if it should exist for whatever reason,
        # ignore it, otherwise report the error
        try:
            os.makedirs(path)
        except OSError as exception:
            if exception.errno == errno.EACCES:
                print_error("[ERROR] You don't have the permission to create directories in '%s'" % os.path.dirname(path))
                return False
            elif exception.errno != errno.EEXIST:
                raise
        return True
    elif not exist:
        print_error("[ERROR] Directory '%s' does not exist" % path)
        return False
    else:
        return True

def check_file(path, file):
    path = os.path.expanduser(path)
    if file is None:
        if not os.path.isfile(path):
            print_error("[ERROR] The file '%s' does not exist!" % (path))
            return False
        else:
            return True
    if not os.path.isfile(get_path(path, file)):
        print_error("[ERROR] The file '%s' does not exist!" % (path + file))
        return False
    else:
        return True

def check_permission(path, permission):
    if check_path(path):
        return os.access(path, permission)
    else:
        return False

def is_readable(path):
    return check_permission(path, os.R_OK)

def is_writeable(path):
    return check_permission(path, os.W_OK)

def format_channel(channel, spaces=True):
    replace = [
        ('etap', 'eta\''),
        ('eta', 'η'),
        ('mu', 'µ'),
        ('pi', 'π'),
        ('omega', 'ω'),
        ('rho', 'ρ'),
        ('g', 'γ'),
        ('0', '⁰'),
        ('+', '⁺'),
        ('-', '⁻')
    ]

    for i, j in replace:
        channel = channel.replace(i, j)

    if spaces:
        chan = re.split(r'_', channel)

        try:
            channel = "  {0:<4s} -->  {1}".format(*chan)
        except:
            channel = "  " + channel
    else:
        channel = channel.replace('_', ' --> ')

    return channel

def unit_prefix(number):
    if number >= 1000000000:
        if str(number).count('0') >= 9:
            return re.sub(r"000000000$", "G", str(number))
        else:
            return str(number/1E9) + 'G'
    elif number >= 1000000:
        if str(number).count('0') >= 6:
            return re.sub(r"000000$", "M", str(number))
        else:
            return str(number/1E6) + 'M'
    elif number >= 1000:
        if str(number).count('0') >= 3:
            return re.sub(r"000$", "k", str(number))
        else:
            return str(number/1E3) + 'k'
    else:
        return str(number)

def input_int(message):
    n = input(message + ' ')

    if not n.isdigit():
        print_error("[ERROR] Invalid input! Please make sure to enter only numbers.")
        raise ValueError('Invalid input submitted')

    return int(n)

def max_file_number(lst):
    if not lst:
        return 0
    lst.sort()
    n = re.compile(r'^.+_(\d+)(_mkin)?\..*$')
    match = n.search(lst[-1])
    if match is not None:
        return int(match.group(1))
    else:
        return 0

def get_path(path, file=None):
    if file:
        return os.path.expanduser(pjoin(path, file))
    else:
        return os.path.expanduser(path)

def replace_all(file, search_exp, replace_exp, number_replacements=0):
    if number_replacements < 0:
        raise ValueError('Negative number of replacements submitted')

    if number_replacements:
        counter = 0
    for line in fileinput.input(file, inplace=True):
        if search_exp in line:
            if number_replacements:
                if counter == number_replacements:
                    continue
                else:
                    counter += 1
            line = replace_exp
            #line = line.replace(search_exp, replace_exp)
        print(line, end='')

def replace_line(file, search_exp, replace_exp):
    replace_all(file, search_exp, replace_exp, 1)

def run(cmd, logfile, error=False):
    if error:
        p = subprocess.Popen(cmd, shell=True, universal_newlines=True, stdout=logfile, stderr=logfile)
    else:
        p = subprocess.Popen(cmd, shell=True, universal_newlines=True, stdout=logfile)
    #ret_code = p.wait()
    #logfile.flush()
    return p.wait()

def timestamp():
    return '[%s] ' % str(datetime.datetime.now()).split('.')[0]

def write_current_info(filename, string):
    try:
        with open(filename, 'w') as f:
            f.write(string)
    except:
        raise


def check_goat():
    if not check_path(GOAT_PATH):
        print("        Please make sure your goat directory can be found at the given path.")
        return False
    goat_bin = get_path(GOAT_BUILD, 'bin')
    if not check_file(goat_bin, GOAT_BIN):
        print("        Could not find the specified executable '%s'." % GOAT_BIN)
        print("        Please make sure the defined executable is correct.")
        return False
    bin = get_path(goat_bin, GOAT_BIN)
    if GOAT_CONFIG == '/dev/null':
        config = '/dev/null'
    elif not check_file(GOAT_PATH, GOAT_CONFIG):
        print("        Could not find your specified goat config file.")
        return False
    else:
        config = get_path(GOAT_PATH, GOAT_CONFIG)
    return bin, config

def is_valid_file(parser, arg):
    if not os.path.isfile(arg):
        parser.error('The file %s does not exist!' % arg)
    else:
        return open(arg, 'r')

def is_valid_dir(parser, arg):
    if not os.path.isdir(os.path.expanduser(arg)):
        parser.error('The directory %s does not exist!' % arg)
    else:
        return os.path.expanduser(arg)

def sort_channels(file_list, pattern):
    sorted_channels = {}
    regex = re.compile(pattern)
    for filename in file_list:
        match = regex.search(os.path.basename(filename))
        if match:
            channel = match.group(1)
            if channel not in sorted_channels.keys():
                sorted_channels.update({channel: []})
            sorted_channels[channel].append(filename)
    return sorted_channels

def merge_files(input_files, prefix, output_directory):
    merged_files = []
    for chan, lst in input_files.items():
        merged = prefix + '_' + chan + '_merged.root'
        merged = get_path(output_directory, merged)
        cmd = 'hadd ' + merged
        for f in lst:
            cmd += ' ' + f
        #print(cmd)
        merged_files.append(merged)
    return merged_files

# calculate the dimensions which are used to divide the canvas
# the ratio determines the dimensions, ratio of the length to the height
# ratio of 1 is for a square layout
def get_dimensions(size, ratio=1.2):
    if size == 1:
        cols, rows = 1, 1
    else:
        cols = ceil(sqrt(size)*ratio)
        rows = ceil(size/cols)

    return cols, rows

def flatten(lst):
    from itertools import chain
    new_list = list(chain(*lst))  # flatten a list of type [[1, 2], [3, 4]] to [1, 2, 3, 4]
    # do this recursively until the list contains no more lists
    if any(isinstance(sublist, list) for sublist in new_list):
        return flatten(new_list)
    else:
        return new_list

def main():
    #sys.argv

    parser = argparse.ArgumentParser(description='Analyse simulation files')
    parser.add_argument('-f', '--file-list', nargs=1, metavar='file', dest='filename',
            type=lambda x: is_valid_file(parser, x), #argparse.FileType('r'), #required=True
            help='file with a list of simulation files which should be analysed; cannot be used together with --dir')
    parser.add_argument('-d', '--dir', nargs=1, metavar='directory',
            type=lambda x: is_valid_dir(parser, x),
            help='directory containing the files which should be analysed; cannot be used together with --file-list')
    parser.add_argument('-o', '--output', nargs=1, metavar='directory',
            type=lambda x: is_valid_dir(parser, x),
            help='output directory where all analysed / merged files will be stored as well as plots')
    parser.add_argument('-m', '--merge', action='store_true',
            help='merge files automatically according to their channel')
    parser.add_argument('-a', '--analyse', action='store_true',
            help='analyse merged files instead of terminating; only needed in combination with -m or --merge')
    parser.add_argument('-j', '--merge-analysis', action='store_true',
            help='merge (join) single analysed files for each channel into one file')
    parser.add_argument('-p', '--plot', nargs='+', metavar='histogram name',
            help='the name of the histogram(s) which should be plotted for each file')
    # possible options: s -> skip analysis, only plot stuff; l -> list possible histograms from file
    parser.add_argument('-v', '--verbose', action='store_true',
            help='print logging output to the terminal')
    #parser.add_argument()

    args = parser.parse_args()
    dir = None
    file = None
    output = None
    merge = args.merge
    analyse = args.analyse and merge
    merge_analysis = args.merge_analysis
    plots = args.plot
    verbose = args.verbose
    if args.filename: #args.file_list:
        file = args.filename[0] #args.file_list[0]
        #print(file)
        print('use file ' + file.name)
    if args.dir:
        dir = args.dir[0]
        print('use directory ' + dir)
    if dir and file:
        sys.exit('Use either --dir or --file-list, not both')
    if not dir and not file:
        print("You've specified neither a file nor a directory. INPUT_DATA_PATH will be used.")
        if not check_path(INPUT_DATA_PATH):
            sys.exit("        Please make sure the specified input directory INPUT_DATA_PATH exists.")
        else:
            dir = get_path(INPUT_DATA_PATH)
    if args.output:
        output = args.output[0]
    else:
        print('No output directory specified, will use OUTPUT_DATA_PATH')
        if not check_path(OUTPUT_DATA_PATH, True):
            sys.exit('        Please make sure the specified output directory OUTPUT_DATA_PATH exists.')
        else:
            output = get_path(OUTPUT_DATA_PATH)

    if dir:
        input_files = os.listdir(os.path.expanduser(INPUT_DATA_PATH))
        #TODO: new in Python 3.5: os.scandir() (faster) https://docs.python.org/dev/library/os.html#os.scandir
    elif file:
        input_files = file.readlines()
        for line in input_files:
            if len(line.split()) != 1:
                file.close()
                sys.exit('There should be only a listing of files in the input file you specified, nothing more!')
            else:
                print('+++ read file, line: ' + line)
                if not check_file(line, None):
                    print("        The file '%s' doesn't exist, it will be skipped." % line)
                    input_files.remove(line)
        if not input_files:
            file.close()
            sys.exit("The input file list is empty, will terminate.")
        file.close()
    else:
        sys.exit("Neither directory nor file-list exists. This shouldn't happen.")

    output_files = []
    channels = []
    input_channels = {}
    output_channels = {}
    prefix = INPUT_FILE_PREFIX
    pattern = '^' + prefix + '_(.+)_\d+.root$'
    #regex = re.compile(pattern)
    #for filename in input_files:
    #    match = regex.search(filename)
    #    if match is not None and match.group(1) not in channels:
    #        channels.append(match.group(1))
    #        input_channels.update({match.group(1): []})#(match.group(1)=[]) python doesn't like this, because it expects sth like update(key=value) and match.group(1) is an expression, thus update has to be used with a new dict {'key': value}
    #    if match:
    #        input_channels[match.group(1)].append(filename)
    input_channels = sort_channels(input_files, pattern)
    channels = input_channels.keys()
    print('Found %d different channels:' % len(channels))
    if verbose:
        for chan in channels:
            try:
                print('   ' + format_channel(chan, False))
            except:
                print('   ' + chan)
        print()
    for chan, lst in input_channels.items():
        #n = max_file_number(lst)
        try:
            chan = format_channel(chan, False)
        except:
            None
        print(chan, ' (%d files)' % len(lst))
        if verbose:
            for f in lst:
                print('   ' + f)
    if merge:
        prefix = 'Goat'
        if prefix is INPUT_FILE_PREFIX:
            prefix += '_'
        merged_files = merge_files(input_channels, prefix, output)
        if not analyse:
            sys.exit(0)
        print(merged_files)

    check = check_goat()
    if not check:
        sys.exit(1)
    goat_bin, goat_config = check

    if analyse:
        input_files = merged_files
        pattern = '^' + prefix + '_(.+)_merged.root$'
        input_channels = sort_channels(merged_files, pattern)
    for channel, input_files in input_channels.items():
        output_channels.update({channel: []})
        for input_file in input_files:
            output_file = input_file.replace(prefix, OUTPUT_FILE_PREFIX)
            cmd = ' '.join([goat_bin, goat_config, input_file, output_file])
            print(cmd)
            output_channels[channel].append(output_file)

    if merge_analysis:
        output_channels = merge_files(output_channels, OUTPUT_FILE_PREFIX, output)
    print(output_channels)
    sys.exit(0)
    # terminate at this point if no plots should be created
    if not plots:
        sys.exit(0)

    if ROOTSYS:
        #os.environ['ROOTSYS'] = ROOTSYS
        #os.environ['PYTHONPATH'] = ROOTSYS + '/lib:' + os.environ['PYTHONPATH']
        # The Python interpreter is already running, so we can't just simply
        # set environment variables via os.environ['VARABLE_NAME']. Instead
        # we have to append them to the path which Python actually uses to
        # search for packages
        #sys.path.append(ROOTSYS + '/lib')
        # use insert instead of append to add the entry at the beginnging of
        # the list to be sure it is used prioritised
        sys.path.insert(0, ROOTSYS + '/lib')
        if verbose:
            print('Added custom ROOTSYS to import ROOT package')
    #print(os.environ['ROOTSYS'])
    #print(os.environ['PYTHONPATH'])
    #print(sys.path)
    #ROOT = ROOTSYS + '/lib/ROOT.py'
    #ROOT = __import__(ROOT)
    from ROOT import gROOT, gStyle, gPad#, gDirectory
    from ROOT import TFile, TDirectoryFile
    from ROOT import TCanvas, TH1D, TH2D, TLegend

    #sys.exit(0)

    #test file
    #file_list = ['/home/wagners/test_out.root']
    #print('start ROOT test processing with list:')
    #print(file_list)

    gROOT.Reset()
    gStyle.SetCanvasColor(0)
    #gPad.SetLogz()
    histograms = {}
    for filename in file_list:
        current = TFile(filename)
        if current.GetListOfKeys().GetSize() > 1:
            print('Found more than one directory in file %s' % current.GetName())
            print('Will use the first one to find the histograms')
            if verbose:
                print('The full list of directories:')
                current.GetListOfKeys().Print()
        elif not current.GetListOfKeys().GetSize():
            print('Found no directory in file %s' % current.GetName())
            print('Will skip this file')
            continue
        dir_name = current.GetListOfKeys().First().GetName()
        #if not current.cd(dir_name):
        #    print("Can't change directory to '%s', will skip this file" % dir_name)
        # by using the above the histograms can only be accessed via the gDirectory pointer, thus get the directory directly
        dir = current.GetDirectory(dir_name)
        #folder = TDirectoryFile(current.Get("ROOT Memory"))  --> not needed, doesn't work anyway... (current.ls() prints structure though...)
        for plot in plots:
            if not plot in histograms.keys():
                histograms.update({plot: []})
            hist = dir.Get(plot)
            if hist == None:  # with pyROOT null pointers has to be explicitly checked with "== None", other checks won't work because of the used internal structure via the Python C-API "rich compare" interface
                print('histogram not found in %s/%s' % (current.GetName(), dir_name))
                continue
            #hist = TH1D(current.FindObjectAny(plot))  # casting TObjects doesn't work, therefore changing the directory is needed...
            histograms[plot].append(copy(hist))
        current.Close()

    if not flatten(histograms.values()):
        sys.exit('No specified histograms found, will terminate')

    output = get_path(output, 'plots')
    if not check_path(output, create=True, silent=False):
        sys.exit("Unable to create folder to store plots")

    for name, hists in histograms.items():
        cols, rows = get_dimensions(len(hists))
        canvas = TCanvas(name)
        canvas.Divide(cols, rows)
        for index, hist in enumerate(hists, start=1):
            canvas.cd(index)
            hist.Draw()
        timestamp = datetime.datetime.now().strftime('_%Y-%m-%d_%H-%M')  # add timestamp to prevent overwriting existing files
        pdfname = get_path(output, name + timestamp + '.pdf')
        canvas.Print(pdfname)

    sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCtrl+C detected, will abort analysis')
        sys.exit(0)
    except Exception as e:
        print('An error occured during execution:')
        print(e)
        sys.exit(1)
