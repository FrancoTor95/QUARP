clear; close all;

% Add utilities folder to the MATLAB path
addpath(genpath('util'));

%% Initialization and Data Loading

% Specify the path to the recorded WAV file
file_name = 'data/sea_trial.wav';

% Optional: Load specific file information if needed (using custom utility)
% info = read_wav_file(file_name);

% Read audio samples and sampling frequency (fs) from the WAV file
[samples, fs] = audioread(file_name);

% Remove the DC offset (zero-mean the signal)
samples = (samples - mean(samples));

% Configure FFT and Spectrogram parameters
fft_length = 8 * 4096;
freq_step = (fs / fft_length);
freq_span = (-(fft_length - 1)/2 : (fft_length - 1)/2) * freq_step;

% Define window size for the spectrogram (1 ms window)
window_size = 0.001 * fs;
% Define overlap between consecutive windows (80% overlap)
overlap = round(0.8 * window_size);

loop_counter = 0;

%% Signal Visualization (Iterative Windowing)
% Iterate through the samples in chunks, advancing by 1 second (fs samples) each step
for i = 1:fs:length(samples) - fs
    
    % Define the start and stop indices for the current 2-second observation window
    start_idx = i;
    stop_idx = start_idx + 2 * fs;
    samples_window = samples(start_idx:stop_idx);
    
    % --- Optional FFT Analysis Setup (Currently Unused/Commented out) ---
    start_fft = round(length(samples_window) * 3/4);
    samples_window2 = [];
    for k = 1:7
        samples_window2 = [samples_window2; samples_window(start_fft:start_fft+750)];
    end

    fft_result2 = fftshift(fft([samples_window(start_fft:start_fft+750); zeros(fft_length - 750, 1)], fft_length));
    fft_result_abs2 = abs(fft_result2);
    max_fft_result_abs2 = max(fft_result_abs2);
    
    fft_result = fftshift(fft(samples_window2, fft_length));
    fft_result_abs = abs(fft_result);
    max_fft_result_abs = max(fft_result_abs);
    % -------------------------------------------------------------------

    % Setup the main figure and tiled layout for synchronized plotting
    figure(1); clf;
    tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
    
    %% First Subplot: Spectrogram
    ax1 = subplot(2, 1, 1);
    
    % Calculate and display the spectrogram
    % Note on parameters:
    % - Frequency resolution = fs / window_size
    % - fft_length: Defines FFT interpolation points. If window_size < fft_length, 
    %   zero-padding is applied.
    % - A longer window_size yields higher frequency resolution but lower time resolution.
    % - A shorter window_size yields higher time resolution but lower frequency resolution.
    spectrogram(samples_window, ...
        blackmanharris(window_size), ...
        overlap, ...
        fft_length, ...
        fs, ...
        'yaxis');
    
    title('Spectrogram');
    ylabel('Frequency (kHz)');
    xlabel('Time (s)');

    % Retrieve the internal time vector from the spectrogram to synchronize axes later
    [~, f_spect, t_spect, ~] = spectrogram(samples_window, blackmanharris(window_size), overlap, fft_length, fs);
    
    %% Second Subplot: Time Domain Signal
    ax2 = subplot(2, 1, 2);
    
    % Create a time vector for the current window and plot the raw signal
    time_vec = (0:length(samples_window)-1) / fs;
    plot(time_vec, samples_window);
    grid on;
    xlabel('Time (s)');
    ylabel('Amplitude');
    title('Time Domain Signal');
    
    %% Axes Synchronization
    % Calculate the temporal shift introduced by the spectrogram windowing
    dt = (window_size - overlap) / fs;     % Time step between consecutive windows
    t_start = t_spect(1) - dt/2;           % First time instance shown in the spectrogram
    t_end = t_spect(end) + dt/2;           % Last time instance shown in the spectrogram
    
    % Perfectly synchronize the X-axis (time) of both subplots
    linkaxes([ax1, ax2], 'x');
    xlim([t_start, t_end]);

    % --- Optional FFT Plotting (Commented out) ---
    % figure(2)
    % plot(freq_span, fft_result_abs)
    % hold on
    % plot(freq_span, fft_result_abs2)
    % title('FFT on the overall window')
    % xlabel('Frequency (Hz)');
    % ylabel('Magnitude');
    % grid on
    % ---------------------------------------------
    
    % Break the loop after displaying 3 windows to prevent infinite rendering
    loop_counter = loop_counter + 1;
    if (loop_counter == 3)
        break;
    end
    
    % Pause execution and wait for user input (key press) to proceed to the next window
    pause;
end