import numpy as np
from scipy.optimize import least_squares

# Parameters
SPEED_SOUND = 1498  # m/s, speed of sound in water

noise_std = 0
DEFAULT_FS = 300_000
DEFAULT_TS = 1 / DEFAULT_FS
DEFAULT_CENTER_INDEX = 1800
SHOW_TRUTH = True  # set to False to hide ground truth in the plot

# Microphones placed at the corners of a square with 2 m diagonal
""" DEFAULT_MIC_POSITIONS = np.array([
    [-0.707, -0.707],
    [-0.707,  0.707],
    [ 0.707,  0.707],
    [ 0.707, -0.707]
])
 """
DEFAULT_MIC_POSITIONS = np.array([
    [1, 0],
    [0,  -1],
    [ -1,  0],
    [ 0, 1]
])

# Sources located on a circle of radius 10 m
sources = np.array([
    [20*np.cos(theta), 20*np.sin(theta)]
    for theta in np.linspace(0, 2 * np.pi, 40)
])

# --- Residual function for least-squares solver ---
def residuals(params, mic_positions, tdoa, v):
    x, y, t0 = params  # also estimate time bias t0
    # compute distances and normalize to first mic
    dists = np.linalg.norm(mic_positions - [x, y], axis=1)
    d0 = dists[0]
    pred_tdoa = (dists - d0) / v + t0
    return pred_tdoa - tdoa

# --- Analytic Jacobian of the residuals ---
def jacobian(params, mic_positions, toa, v):
    x, y, t0 = params
    dists = np.linalg.norm(mic_positions - [x, y], axis=1)
    d0 = dists[0]
    n = len(dists)
    J = np.zeros((n, 3))
    # derivatives wrt x and y
    for i in range(n):
        if dists[i] == 0 or d0 == 0:
            J[i, 0] = 0
            J[i, 1] = 0
        else:
            J[i, 0] = ((x - mic_positions[i,0]) / dists[i] -
                       (x - mic_positions[0,0]) / d0) / v
            J[i, 1] = ((y - mic_positions[i,1]) / dists[i] -
                       (y - mic_positions[0,1]) / d0) / v
    # derivative wrt t0
    J[:, 2] = 1
    return J

# --- Position estimation function (TOA/TDOA + t0) with analytic Jacobian ---
def localize_source(events, mic_positions=DEFAULT_MIC_POSITIONS,
                    v_sound=SPEED_SOUND, initial_guess=None):
    if initial_guess is None:
        initial_guess = np.array([0.0, 0.0, 0.0])
    result = least_squares(
        residuals,
        initial_guess,
        jac=jacobian,
        args=(mic_positions, events, v_sound)
    )
    return result.x[:2], result.x[2]   # return (x, y), t0

def estimate_aoa(correl_indices,
                 mic_positions = DEFAULT_MIC_POSITIONS,
                 c = SPEED_SOUND,
                 Ts = DEFAULT_TS,
                 center_index = DEFAULT_CENTER_INDEX):
    """
    Stima AoA (2D far-field) mantenendo d_i = u·(m_i - m_0).
    correl_indices: indici di correlazione [0..N]
    mic_positions: array (M,2)
    c: velocità suono
    Ts: periodo di campionamento
    center_index: indice di riferimento (es. 1800)
    """
    # 1) da indici a tau_i = (idx_i - idx_0)*Ts
    correl = np.clip(correl_indices, 0, None)
    tau = (correl - correl[0])*Ts   # tau[0] = 0

    # 2) costruzione di A e b
    M = mic_positions.shape[0]
    A = np.zeros((M-1, 2))
    b = np.zeros(M-1)
    for i in range(1, M):
        delta = mic_positions[i] - mic_positions[0]
        A[i-1, :] = delta
        b[i-1]    = c * tau[i]

    # 3) risolvi min ||A u - b||^2
    u_hat, *_ = np.linalg.lstsq(A, b, rcond=None)

    # 4) angolo di arrivo
    theta = np.arctan2(u_hat[1], u_hat[0]) + np.pi
    return theta*(180/np.pi)

def estimate_aoa_compensated(correl_indices, yaw, pitch, roll,
                             mic_positions=DEFAULT_MIC_POSITIONS,
                             c=SPEED_SOUND,
                             Ts=DEFAULT_TS,
                             center_index=DEFAULT_CENTER_INDEX):
    """
    Stima AoA (2D far-field) compensando l'inclinazione (Pitch/Roll) e rotazione (Yaw).
    Se yaw=0, l'angolo restituito è relativo al Nord "virtuale" del corpo (tilt-compensated).
    Se yaw=Heading, l'angolo restituito è Absolute Bearing (riferito al Nord).
    """
    # 1) da indici a tau_i
    correl = np.clip(correl_indices, 0, None)
    tau = (correl - correl[0])*Ts   # tau[0] = 0

    # 2) Costruzione matrice di rotazione Body -> NED (Yaw-Pitch-Roll convention)
    # Converti gradi in radianti
    y_rad = np.radians(yaw)
    p_rad = np.radians(pitch)
    r_rad = np.radians(roll)
    
    cy, sy = np.cos(y_rad), np.sin(y_rad)
    cp, sp = np.cos(p_rad), np.sin(p_rad)
    cr, sr = np.cos(r_rad), np.sin(r_rad)

    # Rz (Yaw)
    Rz = np.array([
        [cy, -sy, 0],
        [sy,  cy, 0],
        [ 0,   0, 1]
    ])
    # Ry (Pitch)
    Ry = np.array([
        [ cp, 0, sp],
        [  0, 1,  0],
        [-sp, 0, cp]
    ])
    # Rx (Roll)
    Rx = np.array([
        [1,   0,   0],
        [0,  cr, -sr],
        [0,  sr,  cr]
    ])
    
    # R_body_to_ned = Rz * Ry * Rx
    R = Rz @ Ry @ Rx

    # 3) Proiezione posizioni microfoni
    # Estendi a 3D (z=0 nel body frame)
    M = mic_positions.shape[0]
    mics_body_3d = np.hstack([mic_positions, np.zeros((M, 1))])
    
    # Ruota nel frame inerziale (NED)
    # P_ned = R * P_body^T -> trasposto per avere righe (N,3)
    mics_ned = (R @ mics_body_3d.T).T
    
    # 4) Risoluzione LS usando coordinate X,Y "virtuali" nel frame NED
    # (Assumendo sorgente sul piano orizzontale inerziale z=0)
    A = np.zeros((M-1, 2))
    b = np.zeros(M-1)
    
    # Mic 0 è il riferimento
    m0_ned = mics_ned[0]
    
    for i in range(1, M):
        # Delta posizione nel piano orizzontale NED
        delta = mics_ned[i, :2] - m0_ned[:2]
        A[i-1, :] = delta
        b[i-1]    = c * tau[i]

    # 5) risolvi min ||A u - b||^2
    u_hat, *_ = np.linalg.lstsq(A, b, rcond=None)

    # 6) angolo di arrivo (Bearing/Azimuth in frame NED)
    theta = np.arctan2(u_hat[1], u_hat[0]) + np.pi
    return theta*(180/np.pi)


def estimate_aoa_delta_t(correl_indices,
                 mic_positions = DEFAULT_MIC_POSITIONS,
                 c = SPEED_SOUND,
                 Ts = DEFAULT_TS,
                 center_index = DEFAULT_CENTER_INDEX):
    """
    Stima AoA (2D far-field) mantenendo d_i = u·(m_i - m_0).
    correl_indices: indici di correlazione [0..N]
    mic_positions: array (M,2)
    c: velocità suono
    Ts: periodo di campionamento
    center_index: indice di riferimento (es. 1800)
    """
    # 1) da indici a tau_x = (idx_2 - idx_0)*Ts tau_y = (idx_3 - idx_1)*Ts
    correl = np.clip(correl_indices, 0, None)
    tau_x = (correl[2] - correl[0])*Ts
    tau_y = (correl[3] - correl[1])*Ts

    # 2) angolo di arrivo
    theta = np.arctan2(tau_y, tau_x)
    return -theta*(180/np.pi)

def estimate_azimut(correl_indices,
                 mic_positions = DEFAULT_MIC_POSITIONS,
                 c = SPEED_SOUND,
                 Ts = DEFAULT_TS,
                 center_index = DEFAULT_CENTER_INDEX):
    """
    Stima AoA (2D far-field) mantenendo d_i = u·(m_i - m_0).
    correl_indices: indici di correlazione [0..N]
    mic_positions: array (M,2)
    c: velocità suono
    Ts: periodo di campionamento
    center_index: indice di riferimento (es. 1800)
    """
    # 1) da indici a tau_x = (idx_2 - idx_0)*Ts tau_y = (idx_3 - idx_1)*Ts
    correl = np.clip(correl_indices, 0, None)
    tau_x = (correl[2] - correl[0])*Ts
    tau_y = (correl[3] - correl[1])*Ts

    # 2) angolo di arrivo
    phi = np.acos(SPEED_SOUND*np.sqrt(tau_x*tau_x + tau_y*tau_y)/2)
    return phi*(180/np.pi)


# --- Convert correlation indices to TDOA (relative time) ---
def correlation_to_time(correl_indices, center_index=DEFAULT_CENTER_INDEX,
                        Ts=DEFAULT_TS):
    correl_indices = np.clip(correl_indices, 0, 3600)
    return (correl_indices - correl_indices[0]) * Ts

# --- Simulate correlation indices from a source position ---
def simulate_correl_indices(source, mic_positions=DEFAULT_MIC_POSITIONS,
                             noise_std=0, ts=DEFAULT_TS,
                             center_index=DEFAULT_CENTER_INDEX):
    dists = np.linalg.norm(mic_positions - source, axis=1)
    toa = dists / SPEED_SOUND
    noisy = toa + np.random.normal(0, noise_std, size=toa.shape)
    correl_indices = (noisy / ts).astype(int)
    correl_indices -= (correl_indices[0] - center_index)
    return correl_indices, toa


def aoa_to_dac_values(theta_deg,
                      mic_positions=DEFAULT_MIC_POSITIONS,
                      c=SPEED_SOUND,
                      ref_idx=0):
    """
    Dato un angolo AoA (gradi, far-field), calcola i valori int16_t da scrivere nel DAC
    per realizzare i ritardi corrispondenti.
    
    Relazione HW: delay_s = x * 15 / 10_000_000  ->  x = delay_s * 10_000_000 / 15
    """
    theta = np.deg2rad(theta_deg)
    # coerente con estimate_aoa (che aggiunge +pi)
    u = -np.array([np.cos(theta), np.sin(theta)])
    
    m0 = mic_positions[ref_idx]
    tau = np.array([np.dot(mi - m0, u) / c for mi in mic_positions])  # sec
    tau = tau - tau[ref_idx]  # ref = 0
    
    # conversione a valore DAC
    scale = 10_000_000 / 15  # = 666_666.666...
    dac_values = np.rint(tau * scale).astype(np.int16)
    
    return dac_values, tau * 1e6  # ritorno sia valori DAC che ritardi in µs


# --- Main execution block ---
if __name__ == '__main__':
    estimated_positions = []
    for source in sources:
        correl_indices, true_toa = simulate_correl_indices(
            source, noise_std=noise_std)
        tdoa = correlation_to_time(correl_indices)
        
        pos_ls, t0 = localize_source(true_toa)
        estimated_theta = estimate_aoa(correl_indices)
        estimated_theta_delta_t = estimate_aoa_delta_t(correl_indices)
        
        estimated_positions.append(pos_ls)
        err_q = (tdoa - (true_toa - true_toa[0]))*1e6
        dac_vals, delays = aoa_to_dac_values(estimated_theta)
        print(f'DAC shifts: {dac_vals}')
        print(f'Corresponding delays: {delays}')
        #print(f"Max quant err: {np.max(np.abs(err_q)):.2f} µs | t0: {t0*1e3:.3f} ms")
        print(f"\testimated theta = {estimated_theta:.3f}")
        print(f"\testimated theta dt= {estimated_theta_delta_t:.3f}")
        print(f"\treal theta = {(np.atan2(source[1], source[0]))*(180/np.pi):.3f}")
        print(f'Real TOA: {true_toa}')
        print()
