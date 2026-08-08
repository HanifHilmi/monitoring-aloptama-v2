import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import calendar


# ==========================================
# 1. KONFIGURASI BULAN & FOLDER
# ==========================================
TAHUN = 2026
BULAN = 7       # Ganti dengan bulan yang ingin dianalisa (1 = Januari)
FOLDER_PATH = "mnt/cdp1_logs/oneminute" # Nama folder penyimpanan file .dat

# Format YYYYMM untuk mencari file, misal: "202601"
target_yyyymm = f"{TAHUN}{BULAN:02d}"

# ==========================================
# 2. DEFINISI SENSOR AWOS KATEGORI III (RHF)
# ==========================================
slices = [
    (0, 3, "STN"), (4, 12, "Date"), (13, 15, "Hour"), (16, 18, "Minute"),
    (19, 23, "WS_04_kt"), (24, 28, "WD_04_deg"), (29, 33, "WGS_04_kt"), (34, 38, "WGD_04_deg"),
    (39, 43, "WS_M_kt"), (44, 48, "WD_M_deg"), (49, 53, "WGS_M_kt"), (54, 58, "WGD_M_deg"),
    (59, 63, "WS_22_kt"), (64, 68, "WD_22_deg"), (69, 73, "WGS_22_kt"), (74, 78, "WGD_22_deg"),
    (79, 83, "TEMP_04_degC"), (84, 88, "DEWP_04_degC"), (89, 93, "RH_04_pct"),
    (94, 98, "TEMP_M_degC"), (99, 103, "DEWP_M_degC"), (104, 108, "RH_M_pct"),
    (109, 113, "TEMP_22_degC"), (114, 118, "DEWP_22_degC"), (119, 123, "RH_22_pct"),
    (124, 129, "QNH_04_hPa"), (130, 135, "QNH_M_hPa"), (136, 141, "QNH_22_hPa"),
    (142, 147, "DA_04_ft"), (148, 153, "DA_M_ft"), (154, 159, "DA_22_ft"),
    (160, 165, "ALS_04_cd"), (166, 169, "Day_Night"),
    (170, 175, "VIS_04_m"), (176, 181, "RVR_04_m"),
    (182, 185, "RLS_04_Edg"), (186, 189, "RLS_04_Ctr"), (190, 193, "RLS_04_Man"),
    (194, 199, "VIS_22_m"), (200, 205, "RVR_22_m"),
    (206, 209, "RLS_22_Edg"), (210, 213, "RLS_22_Ctr"), (214, 217, "RLS_22_Man"),
    (218, 222, "LR1_04_100ft"), (223, 227, "LR1_22_100ft"),
    (228, 257, "SKY_04"), (258, 287, "SKY_22"),
    (288, 293, "RA_04_mm"), (294, 299, "RA_M_mm"), (300, 305, "RA_22_mm"),
    (306, 315, "PW_04"), (316, 325, "PW_22"),
    (326, 331, "SOL_M_Wm2"), (332, 336, "LTX_M")
]

SITE_CONFIG = {
    "RWY 04": {
        'TRH': ['TEMP_04_degC', 'RH_04_pct'],
        'Barometer': ['QNH_04_hPa'],
        'Anemometer': ['WS_04_kt', 'WD_04_deg'],
        'RVR & Vis & ALS': ['RVR_04_m', 'VIS_04_m', 'ALS_04_cd'],
        'Ceilometer': ['SKY_04'],
        'Present Weather': ['PW_04']
    },
    "MIDDLE": {
        'TRH': ['TEMP_M_degC', 'RH_M_pct'],
        'Barometer': ['QNH_M_hPa'],
        'Anemometer': ['WS_M_kt', 'WD_M_deg'],
        'Tipping Bucket': ['RA_M_mm'],
        'Solar Radiation': ['SOL_M_Wm2'],
        'Lightning Detector': ['LTX_M']
    },
    "RWY 22": {
        'TRH': ['TEMP_22_degC', 'RH_22_pct'],
        'Barometer': ['QNH_22_hPa'],
        'Anemometer': ['WS_22_kt', 'WD_22_deg'],
        'RVR & Vis': ['RVR_22_m', 'VIS_22_m'],
        'Ceilometer': ['SKY_22'],
        'Present Weather': ['PW_22']
    }
}

# Sensor event/teks (bukan numerik kontinu)
EVENT_SENSORS = ['PW_04', 'PW_22', 'LTX_M', 'SKY_04', 'SKY_22']

# ==========================================
# 3. BACA DATA HANYA UNTUK 1 BULAN
# ==========================================
print(f"Mencari data untuk periode: {target_yyyymm}...")
# Cuma ambil file yang ada pattern YYYYMM (cth: 202601)
search_pattern = os.path.join(FOLDER_PATH, f"*{target_yyyymm}*.dat")
month_files = glob.glob(search_pattern)

if not month_files:
    raise FileNotFoundError(f"Tidak ada file dengan format {target_yyyymm} di '{FOLDER_PATH}'")

print(f"Ditemukan {len(month_files)} file. Mulai memproses...")

parsed_data = []
for file in month_files:
    with open(file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()[4:] # Abaikan 4 baris pertama (header bawaan)
        for line in lines:
            if not line.strip(): continue
            padded_line = line.ljust(350, " ")
            row = [padded_line[s[0]:s[1]].strip() for s in slices]
            parsed_data.append(row)

col_names = [s[2] for s in slices]
df = pd.DataFrame(parsed_data, columns=col_names)

# Cleaning string kosong & error AWOS
df = df.replace(r'^\s*$', np.nan, regex=True)
df = df.replace(['///', '//', 'MM', 'M', 'N/A', '---'], np.nan)

# Konversi kolom Waktu
df['Datetime'] = pd.to_datetime(df['Date'] + ' ' + df['Hour'] + ':' + df['Minute'], format='%Y%m%d %H:%M', errors='coerce')
df = df.dropna(subset=['Datetime']).drop_duplicates(subset=['Datetime'])
df.set_index('Datetime', inplace=True)
df.sort_index(inplace=True)

# Paksa tipe numerik ke Float (dan skala nilai suhu/tekanan dibagi 10)
numeric_cols = [c for c in df.columns if c not in EVENT_SENSORS + ['STN', 'Date', 'Hour', 'Minute', 'Day_Night']]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')
    # AWOS biasanya mencetak suhu/tekanan tanpa titik desimal (257 = 25.7)
    if 'degC' in col or 'hPa' in col:
        df[col] = df[col] / 10

# ==========================================
# 4. REINDEXING 1 BULAN PENUH
# ==========================================
last_day = calendar.monthrange(TAHUN, BULAN)[1]
start_time = pd.Timestamp(year=TAHUN, month=BULAN, day=1, hour=0, minute=0)
end_time = pd.Timestamp(year=TAHUN, month=BULAN, day=last_day, hour=23, minute=59)

full_range = pd.date_range(start=start_time, end=end_time, freq='min')
df = df.reindex(full_range)
df['Day'] = df.index.day

total_minutes = len(df) # Total menit aktual (misal: 44.640 menit untuk Januari)

# ==========================================
# 5. PERHITUNGAN OLA
# ==========================================
site_stats = {}
sensor_stats = {}

for site_name, sensors in SITE_CONFIG.items():
    # Ambil kolom numerik saja untuk ngecek mati total (System Down)
    site_num_cols = [col for group in sensors.values() for col in group if col not in EVENT_SENSORS]
    
    # Kolom Penanda Site Down (Mati jika semua sensor utamanya NaN)
    df[f'SysDown_{site_name}'] = df[site_num_cols].isna().all(axis=1)
    
    site_downtime = df[f'SysDown_{site_name}'].sum()
    site_uptime = total_minutes - site_downtime
    site_stats[site_name] = {
        'Uptime_pct': (site_uptime/total_minutes)*100, 
        'Down_min': site_downtime
    }
    
    sensor_stats[site_name] = {}
    for comp_name, comp_cols in sensors.items():
        if comp_name in ['Present Weather', 'Lightning Detector']:
            # Pengecualian event: downtime = downtime sistem utama
            comp_down = site_downtime
        else:
            comp_down = df[comp_cols].isna().all(axis=1).sum()
            
        comp_up = total_minutes - comp_down
        sensor_stats[site_name][comp_name] = {
            'Uptime_pct': (comp_up/total_minutes)*100,
            'Down_min': comp_down
        }

print(f"\n--- HASIL OLA BULAN {start_time.strftime('%B %Y').upper()} ---")
for site in SITE_CONFIG.keys():
    print(f"\n[{site}] Uptime: {site_stats[site]['Uptime_pct']:.2f}% | Downtime: {site_stats[site]['Down_min']} menit")
    for sensor, stats in sensor_stats[site].items():
        print(f"   - {sensor:20}: Uptime {stats['Uptime_pct']:6.2f}% | Downtime {stats['Down_min']} mnt")

# ==========================================
# 6. VISUALISASI GRAFIK
# ==========================================
plt.style.use('seaborn-v0_8-whitegrid')

# GRAFIK 1 & 2: OLA BARS
fig, axes = plt.subplots(1, 2, figsize=(15, 5))

# Plot OLA Sistem Keseluruhan
sites = list(site_stats.keys())
uptimes = [site_stats[s]['Uptime_pct'] for s in sites]
bars1 = axes[0].bar(sites, uptimes, color='seagreen', edgecolor='black')
axes[0].set_title(f'OLA System AWOS - {start_time.strftime("%b %Y")}', fontweight='bold')
axes[0].set_ylim(80, 100.5)
axes[0].set_ylabel('Uptime (%)')
for b in bars1: axes[0].bar_label(bars1, fmt='%.2f%%', padding=3, fontweight='bold')

# Plot Uptime Tiap Sensor (Flat bar grouping)
comp_names, comp_vals, comp_colors = [], [], []
colors = ['royalblue', 'darkorange', 'purple']
for i, site in enumerate(sites):
    for sensor, stats in sensor_stats[site].items():
        comp_names.append(f"{site}\n{sensor}")
        comp_vals.append(stats['Uptime_pct'])
        comp_colors.append(colors[i])

axes[1].bar(comp_names, comp_vals, color=comp_colors, edgecolor='black')
axes[1].set_title('Uptime Tiap Komponen Sensor', fontweight='bold')
axes[1].set_ylim(80, 100.5)
axes[1].tick_params(axis='x', rotation=90, labelsize=8)

plt.tight_layout()
plt.show()


# GRAFIK 3: DOWNTIME PER HARI TIAP SITE
fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
fig.suptitle(f'System Downtime per Hari - {start_time.strftime("%b %Y")}', fontsize=16, fontweight='bold')
days_index = np.arange(1, last_day + 1)

for i, site in enumerate(sites):
    dt_per_day = df[df[f'SysDown_{site}']].groupby('Day').size()
    daily_s = pd.Series(0, index=days_index)
    daily_s.update(dt_per_day)
    
    axes[i].bar(daily_s.index, daily_s.values, color='crimson', edgecolor='black')
    axes[i].set_title(f'Downtime Site: {site}')
    axes[i].set_ylabel('Downtime (Menit)')
    axes[i].grid(axis='y', linestyle='--', alpha=0.7)

plt.xlabel('Tanggal')
plt.xticks(days_index)
plt.tight_layout()
plt.show()


# GRAFIK 4: VISUALISASI TIME SERIES DATA SENSOR TIAP LOKASI
print("\nMenyiapkan Plot Pergerakan Data Sensor per Site...")
for site, sensors in SITE_CONFIG.items():
    # Menghitung jumlah grup sensor untuk bikin grid plot (misal 6 grup = 6 baris)
    num_groups = len(sensors)
    fig, axes = plt.subplots(num_groups, 1, figsize=(14, 2.5 * num_groups), sharex=True)
    fig.suptitle(f'Time Series Data AWOS - {site}', fontsize=16, fontweight='bold')
    
    # Supaya kode tidak error jika axes hanya 1, kita paksa bentuk array
    if num_groups == 1: axes = [axes]
        
    for idx, (comp_name, comp_cols) in enumerate(sensors.items()):
        ax = axes[idx]
        plot_ada = False
        
        for col in comp_cols:
            if col not in df.columns: continue
            data = df[col].dropna()
            if data.empty: continue
            
            if col in EVENT_SENSORS or 'SKY' in col:
                # Sensor Teks (PWX, Ceilometer, LTX) kita plot titik / scatter
                ax.scatter(data.index, data.values, label=col, s=15, alpha=0.6)
                if 'SKY' in col:
                    ax.set_yticks([]) # Hapus label y-axis sandi awan agar tak numpuk hitam
                plot_ada = True
            else:
                # Sensor Numerik (Suhu, Angin, RVR, dll) plot garis / line
                ax.plot(data.index, data.values, label=col, linewidth=1.2)
                plot_ada = True
                
        if plot_ada:
            ax.set_ylabel(comp_name, fontsize=10)
            ax.legend(loc='upper right')
            ax.grid(True, linestyle=':', alpha=0.6)
            
    # Format x-axis untuk menampilkan waktu agar lebih cantik
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2)) # Label per 2 hari
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%b'))
    
    plt.tight_layout()
    plt.show()