function [samples, fs] = read_csv_file(file_name, fs)
%READ_CSV_FILE Reads and resamples time-series data from a CSV file.
%
%   [SAMPLES, FS] = READ_CSV_FILE(FILE_NAME) reads the data from the 
%   specified CSV file using a default sampling frequency of 300 kHz.
%
%   [SAMPLES, FS] = READ_CSV_FILE(FILE_NAME, FS) allows specifying a 
%   custom sampling frequency (FS) in Hz to resample the imported data.
%
%   Inputs:
%       file_name - A string or character vector specifying the path to the CSV file.
%                   The CSV is expected to contain 'V_VO_' (Voltage) and 'Time' columns.
%       fs        - (Optional) Desired sampling frequency in Hz. Default is 300000 (300 kHz).
%
%   Outputs:
%       samples   - A column vector containing the resampled voltage data.
%       fs        - The sampling frequency used for the output data.

    % Set default sampling frequency if not provided
    if (nargin < 2)
        fs = 300000;
    end
    
    % Read the CSV file into a table
    samples_table = readtable(file_name);
    
    % Create a timeseries object from the 'V_VO_' (Voltage) and 'Time' columns
    samples_timeseries = timeseries(samples_table.V_VO_, samples_table.Time);
    
    % Define the new uniform time vector based on the target sampling frequency
    new_time = samples_timeseries.Time(1) : 1/fs : samples_timeseries.Time(end) - 1/fs;
    
    % Resample the timeseries to match the new uniform time grid
    samples_timeseries = resample(samples_timeseries, new_time);
    
    % Extract the raw data array from the resampled timeseries object
    samples = samples_timeseries.Data;
end