# Student Routing & Environmental Footprint Analysis

> A data pipeline that analyzes student exam commutes to estimate the CO2 footprint of "unnecessary" university trips.

## Overview

This project analyzes the environmental impact of students commuting to university exams when the trip might be considered "unnecessary." An unnecessary trip is defined by a policy threshold, such as a student attending an exam but receiving a grade of 1.0 or lower. 

The system takes student grades and postal codes as input, geocodes the locations, and calculates the actual road distance to the university using OpenStreetMap and OSRM routing APIs. It then applies a Multinomial Logit (MNL) model to estimate the probability of the student using different transport modes (Car, Public Transport, Walking).

To provide robust estimates, the system runs Monte Carlo simulations over the transport mode probabilities, outputting the expected CO2 equivalent emissions per course along with 95% confidence intervals.

## Pipeline

1. **Input Data**: Reads student records (postal codes, courses, grades) from a CSV file.
2. **Geocoding**: Converts Greek postal codes to coordinates using the Nominatim (OpenStreetMap) or Photon APIs.
3. **Routing**: Calculates actual road distance and driving duration using the free OSRM API (falling back to straight-line Haversine distance if needed).
4. **Mode Estimation**: Uses an MNL model to estimate the probability of using a car, public transport, or walking based on distance and time.
5. **Simulation**: Runs thousands of Monte Carlo simulations to calculate statistical CO2 footprint distributions for the unnecessary trips.

## Tech Stack

| Layer | Technologies |
|---|---|
| Core Language | Python 3 |
| HTTP Requests | `requests`, `urllib3` |
| Geocoding APIs | Nominatim (OSM), Photon (Komoot) |
| Routing API | OSRM (Project OSRM) |

## Configuration

The project's behavior is controlled by `config.json`. Important options include:

| Option | Category | Description |
|---|---|---|
| `policy.max_unnecessary_grade` | Policy | The maximum grade threshold (e.g., 1.0) for a trip to be deemed "unnecessary". |
| `policy.use_marginal_pt_emissions` | Policy | If `true`, assumes public transport runs regardless of the student, resulting in 0 marginal CO2 emissions. |
| `mnl_model.*` | Model | Parameters for the Multinomial Logit model (ASCs and time sensitivity). |
| `simulation.n_simulations` | Simulation | The number of Monte Carlo iterations to run for confidence intervals. |
| `data.university_tk` | Data | The postal code of the university/exam location. |

## Dataset

The system expects a CSV file located at `data/students_data.csv` (as defined in `config.json`). 
Required columns typically include:
- `onoma_mathimatos`: The course name.
- `tk`: The student's postal code.
- `bathmos`: The student's final grade for the course.

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Getting Started

### 1. Clone the repository

```bash
git clone <repository-url>
cd Student-Routing-Footprint
```

### 2. Create and activate a virtual environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the analysis

Edit `config.json` to adjust the policy thresholds, MNL parameters, or university postal code. Ensure your student data is placed in `data/students_data.csv`.

### 5. Run the project

```bash
python scripts/main.py
```

## Usage

When you run `main.py`, the system will:
1. Load the configuration and student records.
2. Identify unnecessary trips based on the policy threshold.
3. Output a detailed list of students, their course, grade, distance, and estimated transport mode probabilities.
4. Execute the Monte Carlo simulation.
5. Print an environmental impact report showing the total estimated CO2 emissions and a breakdown by course with 95% confidence intervals.

## Limitations and Important Considerations

- **API Rate Limits**: The Nominatim API has a strict rate limit of ~1 request/second. The script includes artificial delays (`time.sleep(1)`) to comply with this policy and caches results to avoid redundant requests.
- **Geocoding Accuracy**: Postal codes provide a regional center rather than a precise residential address, which introduces a margin of error in distance calculations.
- **Routing Limitations**: The OSRM API uses a standard driving profile. If a route cannot be found, the system falls back to straight-line (Haversine) distance.
