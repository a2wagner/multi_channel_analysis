#!/usr/bin/env python
# vim: set ai ts=4 sw=4 sts=4 noet fileencoding=utf-8 ft=python

'''
This python script is intended to analyse a given amount of files
either via a file which contains a listing of the files which should
be analysed or a directory which will be read in. The files will be
sorted according to the pattern which is specified in the main method.
If it's not changed, it will match the files which had been produced
with the simulation chain Python script.
Below are a few constants which have to be changed in order to adapt
the file to your analysis environment on your local computer.

See the help
./analyse.py --help
for more information how to use this script.
'''

#TODO: normalisation?
# clean up Physics_XXX.root files created by goat (maybe check filesize less than 1kB or so...)

# IMPORTANT!
# Change the paths below according to your needs
INPUT_DATA_PATH = '~/git/simulation_chain/merged'
OUTPUT_DATA_PATH = '~/git/analysis/output'
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

def goat_analysis(files, goat_bin, goat_config, output_directory=None, prefix='Analysis', sim_log=None, verbose=False):
    output_channels = {}
    if verbose:
        print_color('\n - - - Starting GoAT analysis with ant - - - \n', RED)
    if sim_log:
        sim_log.write('\n' + timestamp() + ' - - - Starting GoAT analysis with ant - - - \n')
    log_output_path = output_directory
    if not log_output_path:  # if no output_directory is given, the path of the first file will be used for the log file
        log_output_path = os.path.split(get_all_dict_values(files)[0])[0]

    with open(get_path(log_output_path, 'goat.log'), 'w') as log:
        for channel, input_files in files.items():
            output_channels.update({channel: []})
            if verbose:
                print_color('     Processing channel %s' % format_channel(channel, False), GREEN)
            if sim_log:
                sim_log.write('\n' + timestamp() + 'Processing channel %s\n' % format_channel(channel, False))
            for input_file in input_files:
                # make sure that the file contains the specified input prefix,
                # otherwise add 'Analysis_' to the beginning of the file name
                # to prevent overwriting existing files
                path, filename = os.path.split(input_file)
                if prefix not in input_file:
                    if not output_directory:
                        output_file = get_path(path, 'Analysis_' + filename)
                    else:
                        output_file = get_path(output_directory, 'Analysis_' + filename)
                else:
                    output_file = input_file.replace(prefix, OUTPUT_FILE_PREFIX)
                    if not path in output_directory:
                        output_file = get_path(output_directory, filename)
                filename = input_file
                if not verbose:
                    filename = os.path.basename(filename)
                logger.info('Analysing file %s' % filename)
                if sim_log:
                    sim_log.write(timestamp() + 'Analysing file %s\n' % input_file)
                    sim_log.flush()
                cmd = ' '.join([goat_bin, goat_config, input_file, output_file])
                # use -b for batchmode (no graphical output) and -q to exit after processing files
                # print errors to log file due to error outputs like "Info in <PStdData::PStdData()>: (CONSTRUCTOR)" because of Pluto
                ret = run(cmd + ' -b -q', log, True)
                if ret:
                    logger.critical('Non-zero return code (%d), something might have gone wrong' % ret)
                    if sim_log:
                        sim_log.write(timestamp() + 'Non-zero return code (%d), something might have gone wrong\n' % ret)
                        sim_log.flush()
                output_channels[channel].append(output_file)

    if verbose:
        print_color('\nFinished analysis\n', RED)
    if sim_log:
        sim_log.write('\n' + timestamp() + 'Finished analysis\n\n')

    return output_channels

def merge_files(files, output_directory=None, prefix='Merged', sim_log=None, force=False, verbose=False):
    merged_files = []
    if verbose:
        print_color('\n - - - Start merging root files - - - \n', RED)
    if sim_log:
        sim_log.write('\n' + timestamp() + ' - - - Start merging root files - - - \n')
    log_output_path = output_directory
    if not log_output_path:  # if no output_directory is given, the path of the first file will be used for the log file
        log_output_path = os.path.split(get_all_dict_values(files)[0])[0]

    with open(get_path(log_output_path, 'hadd.log'), 'w') as log:
        for channel, input_files in files.items():
            merged = prefix + '_' + channel + '_merged.root'
            if verbose:
                print_color('     Processing channel %s' % format_channel(channel, False), GREEN)
            logger.info('Merging file %s' % merged)
            if sim_log:
                sim_log.write('\n' + timestamp() + 'Processing channel %s\n' % format_channel(channel, False))
            if output_directory:
                merged = get_path(output_directory, merged)
            else:
                merged = get_path(log_output_path, merged)

            if force:
                cmd = 'hadd -f '
            else:
                cmd = 'hadd '
            cmd += merged + ' ' + ' '.join(input_files)
            ret = run(cmd, log, True)  # print errors to the log file because of missing PParticle dictionary
            if ret:
                logger.critical('Non-zero return code (%d), something might have gone wrong' % ret)
                if sim_log:
                    sim_log.write(timestamp() + 'Non-zero return code (%d), something might have gone wrong\n' % ret)
                    sim_log.flush()
            merged_files.append(merged)

    if verbose:
        print_color('\nFinished merging files\n', RED)
    if sim_log:
        sim_log.write('\n' + timestamp() + 'Finished merging files\n\n')

    return merged_files

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
        else:
            if 'misc' not in sorted_channels.keys():
                sorted_channels.update(misc=[])
            sorted_channels['misc'].append(filename)
    return sorted_channels

def merge_histograms(lst):
    if not lst:
        print_error('Passed empty list!')
        return None
    elif not isinstance(lst, list):
        print_error('The passed object is not a list!')
        return None
    elif len(lst) == 1:
        return lst[0]

    from ROOT import TH1, TH2
    merged_histogram = lst[0]
    for hist in lst[1:]:
        if not merged_histogram.Add(hist):
            print_error('Error adding histogram contents...')
            return None

    return merged_histogram

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
    # do this to take care for lists like [[1, 2], [3, 4], 5]
    for index, item in enumerate(lst):
        if not isinstance(item, list):
            lst[index] = [item]
    new_list = list(chain(*lst))  # flatten a list of type [[1, 2], [3, 4]] to [1, 2, 3, 4]
    # do this recursively until the list contains no more lists
    if any(isinstance(sublist, list) for sublist in new_list):
        return flatten(new_list)
    else:
        return new_list

def get_dict_values_from_list(lst):
    new_list = []
    for itm in lst:
        if isinstance(itm, dict):
            new_list.append(list(itm.values()))
        else:
            new_list.append(itm)
    new_list = flatten(new_list)
    return get_all_dict_values(new_list)

def get_all_dict_values(dct):
    # do we have a dict?
    if isinstance(dct, dict):
        vals = list(dct.values())  # use list(dict.values()) to get a list of values instead of a view of the dictionary's values
        if any(isinstance(subitem, dict) for subitem in vals):
            return get_dict_values_from_list(vals)
        elif any(isinstance(subitem, list) for subitem in vals):
            return flatten(vals)
        else:
            return vals
    # if it's not a dict, check for a list containing dicts
    elif isinstance(dct, list) and any(isinstance(subitem, dict) for subitem in dct):
        return get_dict_values_from_list(dct)
    # if there's no list containing dicts, return the given value
    else:
        return dct

def get_root_entries(directory):
    entries = []
    dir_name = ''
    if not directory.IsA().GetName() == 'TFile':
        dir_name = directory.GetName() + '/'
    for key in directory.GetListOfKeys():
        if key.GetClassName() == 'TDirectoryFile':
            subdir = get_root_entries(directory.GetDirectory(key.GetName()))
            entries += [dir_name + subkey for subkey in subdir]
        else:
            entries.append(dir_name + key.GetName())
    return entries

def main():
    #sys.argv

    parser = argparse.ArgumentParser(description='Analyse simulation files')
    parser.add_argument('-i', '--input-files', nargs=1, metavar='file', dest='filename',
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
            help='analyse the files, either the given input files or the merged files if the option -m or --merge is used')
    parser.add_argument('-j', '--merge-analysis', action='store_true',
            help='merge (join) single analysed files for each channel into one file')
    parser.add_argument('-p', '--plot', nargs='+', metavar='histogram name',
            help='the name of the histogram(s) which should be plotted for each file')
    parser.add_argument('-f', '--force', action='store_true',
            help='force recreation of files if they already exist (applies mainly for merging files)')
    parser.add_argument('-l', '--log-option', nargs='+', metavar='logarithmic option',
            help='draw histograms logarithmic, use the following format: nD:xyz with n = dimension; e. g. -l 1D:x 2D:z for logarithmic x-axis in 1D histograms and log. z-axis in 2D histograms')
    parser.add_argument('-s', '--style', nargs=1, metavar='drawing style',
            help='ROOT drawing style for histograms (for example colz)')
    parser.add_argument('-r', '--root-output', nargs=1, metavar='ROOT output filename',
            help='store the produced histograms in a root file with the given name')
    # possible options: s -> skip analysis, only plot stuff; l -> list possible histograms from file
    parser.add_argument('-v', '--verbose', action='store_true',
            help='print logging output to the terminal')
    #parser.add_argument()

    args = parser.parse_args()
    input_dir = None
    input_file_list = None
    output = None
    root_output = None
    style = ''
    log1d, log2d, log3d = '', '', ''
    merge = args.merge
    analyse = args.analyse
    merge_analysis = args.merge_analysis
    plots = args.plot
    force = args.force
    verbose = args.verbose
    # adapt logger level to verbose statement
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    if args.filename:
        input_file_list = args.filename[0]
    if args.dir:
        input_dir = args.dir[0]
    if input_dir and input_file_list:
        logger.error('Use either --dir or --input-files, not both')
        sys.exit(1)
    if not input_dir and not input_file_list:
        logger.info("You've specified neither a file nor a directory as input. INPUT_DATA_PATH will be used.")
        if not check_path(INPUT_DATA_PATH):
            sys.exit("        Please make sure the specified input directory INPUT_DATA_PATH exists.")
        else:
            input_dir = get_path(INPUT_DATA_PATH)
    if merge_analysis and not analyse:
        logger.warning("You specified to merge the analyse files but haven't specified to analyse the files.")
        logger.warning("Will assume that the files should be analysed as well.")
        analyse = True
    if args.output:
        output = args.output[0]
        logger.debug("Use directory '%s' to store the output data" % output)
    else:
        logger.debug('No output directory specified, will use OUTPUT_DATA_PATH')
        if not check_path(OUTPUT_DATA_PATH, True):
            sys.exit('        Please make sure the specified output directory OUTPUT_DATA_PATH exists.')
        else:
            output = get_path(OUTPUT_DATA_PATH)
            logger.debug("Use directory '%s' to store the output data" % output)
    if args.root_output:
        root_output = args.root_output[0]
    if args.style:
        style = args.style[0]
        logger.debug("Use the style '%s' to draw histograms." % style)
    if args.log_option:
        for opt in args.log_option:
            if opt.lower().startswith('1d:'):
                log1d = opt.lower().split(':')[-1]
                if log1d.strip('xy'):
                    logger.warning("Unknown log option for axis '%s' in 1D histogram, will be skipped." % log1d.strip('xy'))
                    log1d = log1d.strip('xy')
                logger.debug('Use logarithmic %s axes for 1D histograms.' % ', '.join(log1d))
            elif opt.lower().startswith('2d:'):
                log2d = opt.lower().split(':')[-1]
                if log2d.strip('xyz'):
                    logger.warning("Unknown log option for axis '%s' in 2D histogram, will be skipped." % log2d.strip('xyz'))
                    log2d = log2d.strip('xyz')
                logger.debug('Use logarithmic %s axes for 2D histograms.' % ', '.join(log2d))
            elif opt.lower().startswith('3d:'):
                log3d = opt.lower().split(':')[-1]
                if log3d.strip('xyz'):
                    logger.warning("Unknown log option for axis '%s' in 3D histogram, will be skipped." % log3d.strip('xyz'))
                    log3d = log3d.strip('xyz')
                logger.debug('Use logarithmic %s axes for 3D histograms.' % ', '.join(log3d))
            else:
                logger.warning("Unknown log-option '%s', will be skipped." % opt)
    if merge and merge_analysis:
        logger.info('You specified both merge and merge_analysis.')
        logger.info('Will skip merge_analysis as the files will be already merged before')
        logger.info("the analysis and merging afterwards won't change anything.")
        merge_analysis = False

    if input_file_list:
        logger.debug("Use file '%s' to read in files" % input_file_list.name)
    elif input_dir:
        logger.debug("Use directory '%s' to read in files" % input_dir)

    if input_dir:
        input_files = [filename for filename in os.listdir(input_dir) if filename.endswith('.root')]
        #TODO: new in Python 3.5: os.scandir() (faster) https://docs.python.org/dev/library/os.html#os.scandir
    elif input_file_list:
        input_files = []
        for line in input_file_list:
            # skip empty lines
            if not line.strip():
                continue
            line = line.strip()
            # skip lines starting with a hash
            if line.startswith('#'):
                continue
            if len(line.split()) != 1:
                input_file_list.close()
                logger.error('There should be only a listing of files in the input file you specified, nothing more!')
                sys.exit(1)
            else:
                if not check_file(line, None):
                    print("        This file will be skipped.")
                elif line.endswith('.root'):
                    input_files.append(line)
                else:
                    logger.warning("The file '%s' seems not to be a root file, it will be skipped." % line)
        if not input_files:
            input_file_list.close()
            logger.error("The input file list is empty, will terminate.")
            sys.exit(1)
        input_file_list.close()
    else:
        logger.error("Neither input-directory nor input-file-list exists. This shouldn't happen.")
        sys.exit(1)

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
    logger.info('Found %d different channels:' % len(channels))
    if verbose:
        for chan in channels:
            try:
                logger.debug('   ' + format_channel(chan, False))
            except:
                logger.debug('   ' + chan)
    for chan, lst in input_channels.items():
        #n = max_file_number(lst)
        try:
            chan = format_channel(chan, False)
        except:
            None
        logger.info('   {0:15s} ({1:d} files)'.format(chan, len(lst)))
        if verbose:
            for f in lst:
                logger.debug('   ' + f)
    if merge:
        prefix = 'Goat'
        if prefix is INPUT_FILE_PREFIX:
            prefix += '_'
        merged_files = merge_files(input_channels, output, prefix=prefix, force=force, verbose=verbose)

    if analyse:
        check = check_goat()
        if not check:
            sys.exit(1)
        goat_bin, goat_config = check

        if merge:
            input_files = merged_files
            pattern = '^' + prefix + '_(.+)_merged.root$'
            input_channels = sort_channels(merged_files, pattern)
        output_channels = goat_analysis(input_channels, goat_bin, goat_config, output, prefix=prefix, verbose=verbose)

        if merge_analysis:
            output_channels = merge_files(output_channels, output, prefix=OUTPUT_FILE_PREFIX, force=force, verbose=verbose)
    # in case no analysis is performed, prepare the dict output_channels for the case of merged files or the raw input files
    elif not analyse and merge:
        output_channels = sort_channels(merged_files, '^' + prefix + '_(.+)_merged.root$')
    else:
        output_channels = sort_channels(input_files, pattern)

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
        logger.debug('Added custom ROOTSYS to import ROOT package')
    #print(os.environ['ROOTSYS'])
    #print(os.environ['PYTHONPATH'])
    #print(sys.path)
    #ROOT = ROOTSYS + '/lib/ROOT.py'
    #ROOT = __import__(ROOT)
    from ROOT import gROOT, gStyle, gPad#, gDirectory
    from ROOT import TFile, TDirectoryFile
    from ROOT import TCanvas, TH1, TLegend

    gROOT.Reset()
    gROOT.SetBatch(1)  # run ROOT in batch mode to not display canvases
    gStyle.SetCanvasColor(0)
    #gPad.SetLogz()
    histograms = {}

    logger.info('Start reading in the file contents to gather the histograms')
    for channel, file_list in output_channels.items():
        for filename in file_list:
            current = TFile(filename)
            if not current.IsOpen():  # only proceed if the file exists and is opened
                logger.error('The file could not be opened, please make sure it exists and is readable')
                continue
            if not current.GetListOfKeys().GetSize():
                logger.critical('The file %s is empty' % current.GetName())
                logger.critical('Will skip this file')
                continue
            #dirs = [d.GetName() for d in current.GetListOfKeys() if d.GetClassName() == 'TDirectoryFile']
            file_entries = get_root_entries(current)
            if verbose:
                logger.debug('The full list of histograms in file %s:' % current.GetName())
                for entry in file_entries:
                    obj = current.Get(entry)
                    logger.debug('  %s: %s (%s)' % (obj.IsA().GetName(), entry, obj.GetTitle()))
            for plot in plots:
                if not plot in histograms.keys():
                    histograms.update({plot: {}})
                if not channel in histograms[plot].keys():
                    histograms[plot].update({channel: []})
                # get a list with histograms which match the current plot
                plot_name = [name for name in file_entries if name.rsplit('/', 1)[-1] == plot]
                if not plot_name:
                    logger.critical("The histogram %s couldn't be found in file %s" % (plot, current.GetName()))
                    continue
                elif len(plot_name) > 1:
                    logger.warning('The histogram %s was found %d times in file %s' % (plot, len(plot_name), current.GetName()))
                    for name in plot_name:
                        logger.warning('  %s' % name)
                    logger.warning('Will only use the first occurence of the histogram: %s', plot_name[0])
                hist = current.Get(plot_name[0])
                if hist == None:  # with pyROOT null pointers have to be explicitly checked with "== None", other checks won't work because of the used internal structure via the Python C-API "rich compare" interface
                    logger.critical('histogram %s not found in %s' % (plot, current.GetName()))
                    continue
                histograms[plot][channel].append(copy(hist))
            current.Close()

    if not get_all_dict_values(histograms):
        logger.error('No specified histograms found, will terminate')
        sys.exit(1)

    output = get_path(output, 'plots')
    if not check_path(output, create=True, silent=True):
        logger.error("Unable to create folder to store plots")
        sys.exit(1)

    # merge histograms which belong to the same channel
    logger.info('Start merging histograms of the same channel')
    for plot, channels in histograms.items():
        for channel, plots in channels.items():
            if len(plots) == 1:
                histograms[plot][channel] = histograms[plot][channel][0]
            elif len(plots) > 1:
                merged_hist = merge_histograms(plots)
                if not merged_hist:
                    logger.error("Something went wrong merging the %s histograms for channel %s" % (plot, channel))
                    sys.exit(1)
                histograms[plot][channel] = merged_hist
                logger.debug('Merged %d %s histograms for channel %s' % (len(plots), plot, channel))
            else:
                logger.critical('No %s histograms found for channel %s' % (plot, channel))
                histograms[plot][channel] = None

    root_out = None
    if root_output:
        root_out = TFile(get_path(output, root_output), 'RECREATE')

    logger.info('Create the plots with the desired histograms')
    for name, hists in histograms.items():
        cols, rows = get_dimensions(len(hists))
        canvas = TCanvas(name)
        canvas.Divide(cols, rows)
        index = 1
        # iterate over sorted dict keys that the histograms have the same order all the time
        for channel in sorted(hists):
            hist = hists[channel]
            canvas.cd(index)
            if hist.IsA().GetName().startswith('TH1') and log1d:
                if 'x' in log1d:
                    gPad.SetLogx()
                if 'y' in log1d:
                    gPad.SetLogy()
            elif hist.IsA().GetName().startswith('TH2') and log2d:
                if 'x' in log2d:
                    gPad.SetLogx()
                if 'y' in log2d:
                    gPad.SetLogy()
                if 'z' in log2d:
                    gPad.SetLogz()
            elif hist.IsA().GetName().startswith('TH3') and log3d:
                if 'x' in log3d:
                    gPad.SetLogx()
                if 'y' in log3d:
                    gPad.SetLogy()
                if 'z' in log3d:
                    gPad.SetLogz()
            hist.SetTitle(channel)
            hist.Draw(style)
            index += 1
        timestamp = datetime.datetime.now().strftime('_%Y-%m-%d_%H-%M')  # add timestamp to prevent overwriting existing files
        pdfname = get_path(output, name + timestamp + '.pdf')
        canvas.Update()
        canvas.Print(pdfname)
        if root_out:
            canvas.Write()

    if root_out:
        logger.info('Write histograms to file %s' % root_out.GetName())
        root_out.Write()
        root_out.Close()

    logger.info('  - - - Finished - - -')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        logger.warning('Ctrl+C detected, will abort analysis')
        sys.exit(0)
    except Exception as e:
        logger.error('An error occured during execution:')
        logger.error(e)
        sys.exit(1)
