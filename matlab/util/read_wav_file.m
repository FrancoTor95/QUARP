function [samples, fs] = read_wav_file(file_name, ad4134_full_scale)
%READ_WAV_FILE Reads and scales audio data from a WAV file.
%
%   [SAMPLES, FS] = READ_WAV_FILE(FILE_NAME) reads audio data from the 
%   specified WAV file. The returned samples are scaled by a default 
%   full-scale voltage of 4.096 V, assuming an AD4134 ADC.
%
%   [SAMPLES, FS] = READ_WAV_FILE(FILE_NAME, AD4134_FULL_SCALE) allows 
%   specifying a custom full-scale voltage to correctly map the normalized 
%   WAV data to physical voltage levels.
%
%   Inputs:
%       file_name         - A string or character vector specifying the path 
%                           to the WAV file.
%       ad4134_full_scale - (Optional) The full-scale voltage of the ADC 
%                           (default is 4.096 V).
%
%   Outputs:
%       samples           - A vector/matrix containing the scaled voltage data.
%       fs                - The sampling frequency of the WAV file in Hz.

    % Set default full-scale voltage if not provided
    if (nargin < 2)
        ad4134_full_scale = 4.096;
    end
    
    % Read the normalized audio data and sampling frequency from the WAV file
    [samples, fs] = audioread(file_name);
    
    % Scale the normalized samples [-1.0, 1.0] to physical voltage levels
    samples = ad4134_full_scale * samples;
end