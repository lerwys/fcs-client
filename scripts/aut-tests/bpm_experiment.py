class BPMExperiment():
 
    def __init__(self, fpga_hostname = 'localhost', rffe_hostname = 'localhost', debug = False):
        self.fpga_hostname = fpga_hostname
        self.rffe_hostname = rffe_hostname
        self.debug = debug
        
        from metadata_parser import MetadataParser
        self.metadata_parser = MetadataParser()

    def load_from_metadata(self, input_metadata_filename):
        # Parse metadata file into a dictionary
        self.metadata_parser.parse(input_metadata_filename)
        self.metadata = self.metadata_parser.options

    def get_metadata_lines(self):
        experiment_parameters = list(self.metadata.keys())
        lines = []
        for key in experiment_parameters:
            lines.append(key + ' = ' + self.metadata[key] + '\n')
        return lines
    
    def run(self, data_filename, datapath):
        verbose = False # FIXME: remove this line in the future

        if datapath == 'adc':
            data_rate_decim_factor = '1'
            acq_channel = '0'
            acq_npts = '100000'
        elif datapath == 'tbt':
            data_rate_decim_factor = self.metadata['adc_sampling_harmonic'].split()[0] # FIXME: data_rate_decim_factor should be ideally read from FPGA
            acq_channel = '1'
            acq_npts = '100000'
        elif datapath == 'fofb':
            data_rate_decim_factor = '1000' # FIXME: data_rate_decim_factor should be ideally read from FPGA
            acq_channel = '3'
            acq_npts = '1000000'

        deswitching_phase_offset = str(int(self.metadata['dsp_deswitching_phase'].split()[0]) - int(self.metadata['rffe_switching_phase'].split()[0]))

        import subprocess
        # Run FPGA configuration commands
        command_argument_list = ['fcs_client']
        command_argument_list.extend(['--setdivclk', self.metadata['rffe_switching_frequency_ratio'].split()[0]])
        command_argument_list.extend(['--setkx', self.metadata['bpm_Kx'].split()[0]])
        command_argument_list.extend(['--setky', self.metadata['bpm_Ky'].split()[0]])
        command_argument_list.extend(['--setphaseclk', deswitching_phase_offset])
        command_argument_list.extend(['--setsw' + self.metadata['rffe_switching'].split()[0]])
        command_argument_list.extend(['--setwdw' + self.metadata['dsp_sausaging'].split()[0]])
        command_argument_list.extend(['--setsamples', acq_npts])
        command_argument_list.extend(['--setchan', acq_channel])
        command_argument_list.extend(['--setfpgahostname', self.fpga_hostname])
        if not self.debug:
            subprocess.Popen(command_argument_list)
        else:
            if verbose:
                print(command_argument_list)

        # Run RFFE configuration commands
        command_argument_list = ['fcs_client']
        command_argument_list.extend(['--setfesw', self.metadata['rffe_switching'].split()[0]])
        att_items = self.metadata['rffe_attenuators'].split(',')
        i = 1
        for item in att_items:
            item.strip()
            command_argument_list.extend(['--setfeatt' + str(i), item.split()[0]])
            i = i+1
        command_argument_list.extend(['--setrffehostname', self.rffe_hostname])
        if not self.debug:
            subprocess.Popen(command_argument_list)
        else:
            if verbose:
                print(command_argument_list)

        # TODO: Check if everything was properly set

        # Timestamp the start of data acquisition
        # FIXME: timestamp should ideally come together with data.
        from time import time
        t = time()

        # Run acquisition
        command_argument_list = ['fcs_client']
        command_argument_list.extend(['--startacq', acq_channel])
        command_argument_list.extend(['--setfpgahostname', self.fpga_hostname])
        if not self.debug:
            p = subprocess.Popen(command_argument_list)
        else:
            if verbose:
                print(command_argument_list)

        # The script execution is blocked here until data acquisition has completed

        # Get the result of data acquisition and write it to data file
        command_argument_list = ['fcs_client']
        command_argument_list.extend(['--getcurve', acq_channel])
        command_argument_list.extend(['--setfpgahostname', self.fpga_hostname])

        # Ensure file path exists
        import os
        path = os.path.dirname(data_filename)
        try:
            os.makedirs(path)
        except OSError as exception:
            if not os.path.isdir(path):
                raise

        f = open(data_filename, 'x')
        if not self.debug:
            p = subprocess.Popen(command_argument_list, stdout=f)
        else:
            f.writelines(['10 11 -9 80\n54 5 6 98\n']);
            if verbose:
                print(command_argument_list)
        f.close()

        # Compute data file signature
        f = open(data_filename, 'r')
        text = f.read()
        f.close()

        import hashlib
        if self.metadata['data_signature_method'].split()[0] == 'md5':
            md = hashlib.md5()
        elif self.metadata['data_signature_method'].split()[0] == 'sha-1':
            md = hashlib.sha1()
        elif self.metadata['data_signature_method'].split()[0] == 'sha-256':
            md = hashlib.sha256()
        md.update(text.encode(f.encoding))
        filesignature = md.hexdigest()

        # Format date and hour as an standard UTC timestamp (ISO 8601)
        from time import strftime, gmtime
        from math import floor
        ns = int(floor((t * 1e9) % 1e9))
        timestamp_start = '%s.%09dZ' % (strftime('%Y-%m-%dT%H:%M:%S', gmtime(t)), ns)

        # Trhow away absolute path of data filename
        data_filename_basename = os.path.basename(data_filename)

        # Build metadata file based on template metadata file and post-processed metadata
        
        config_base_metadata_lines = self.get_metadata_lines()
        
        config_automatic_lines = [];
        config_automatic_lines.append('data_original_filename = ' + data_filename_basename + '\n')
        config_automatic_lines.append('data_signature = ' + filesignature + '\n')
        config_automatic_lines.append('dsp_data_rate_decim_factor = ' + data_rate_decim_factor + '\n')
        config_automatic_lines.append('timestamp_start = ' + timestamp_start + '\n')
        #config_automatic_lines.append('adc_board_temperature = ' + '0' + ' C\n') #TODO: implement ADC temperature read on FPGA
        #config_automatic_lines.append('rffe_board_temperature = ' + '0' + ' C\n') #TODO: implement RFFE temperature read on FPGA

        config_fromfile_lines = []
        config_fromfile_lines.extend(config_base_metadata_lines)
        config_fromfile_lines.extend(config_automatic_lines)

        # Metadata file is placed in the same path and with the same filename as the data file, but with .metadata extension
        from os.path import basename
        output_metadata_filename = os.path.splitext(data_filename)[0] + '.metadata'

        f = open(output_metadata_filename, 'x')
        f.writelines(sorted(config_fromfile_lines))
        f.close()
