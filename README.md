# OSRM & Transit Mobility CO2 Engine

> A student mobility simulation and web dashboard that calculates transportation mode choices and CO2 footprints for universities in Attica using OSRM and a Multinomial Logit Model.

## Overview

This project provides a comprehensive system for modeling student mobility, predicting transportation mode choices, and calculating the environmental CO2 footprint for university commutes in Attica, Greece (including UNIWA, EKPA, EMP, etc.). 

It consists of a web-based interactive map dashboard and a Python-based Monte Carlo simulation. The system leverages the Open Source Routing Machine (OSRM) for accurate routing and a Multinomial Logit (MNL) model to determine the probability of a student choosing a specific mode of transport (car, motorcycle, public transit, or walking).

## Features

- **Interactive Web Dashboard** β€” Visualize optimal routes, transport mode probabilities, and CO2 emissions between any Attica postal code and major university campuses using Leaflet.js.
- **Monte Carlo Simulation** β€” Run bulk simulations on student datasets to estimate the total environmental footprint of exam periods.
- **Multinomial Logit Choice Model** β€” Mathematically predict mode selection based on travel time, wait time, access constraints, and alternative-specific constants.
- **Local Routing Engine** β€” Uses local Dockerized OSRM instances (for driving and walking) for fast and private route calculations, with a built-in Haversine distance fallback if the engine is offline.

## Architecture

The system operates through two main interfaces sharing the same underlying logic:

1. **Frontend (Web App)**: `frontend/index.html` queries the local OSRM APIs and public Nominatim API (for geocoding), calculates route costs, applies the MNL model, and renders the result on a Leaflet map.
2. **Backend Simulation (Python)**: `src/simulate_failing_students_co2.py` reads student data (`data/students_exam_dataset.csv`), queries the OSRM APIs, applies the MNL model, and outputs a detailed CLI report of the aggregated CO2 emissions.

Both interfaces rely on three Dockerized backend instances:
- **Port 5000 (OSRM)**: Driving profile (for cars, motorcycles, buses).
- **Port 5001 (OSRM)**: Walking profile (for pedestrians).
- **Port 8080 (OTP)**: OpenTripPlanner (for real transit schedules and geometry).

## Mode Choice Model

The system uses a Multinomial Logit Model to determine the probability $P(i)$ of choosing a transport mode $i$.

### Generalized Cost ($C_i$)
$$C = t_{\text{travel}} + 1.2 \cdot t_{\text{wait}} + \text{Penalty}_{\text{transfer}} + \text{ASC}$$

### Probability of Selection
$$P(i) = \frac{e^{-\theta \cdot C_i}}{\sum_k e^{-\theta \cdot C_k}}$$

### Emission Factors (g CO₂eq / pax-km)
- 🚗 **Car**: 120.0
- 🛵 **Motorcycle**: 70.0
- 🚌 **Bus**: 10.81
- 🚇 **Metro**: 3.1
- 🚶 **Walking**: 0.0

## Tech Stack

| Layer | Technologies |
|---|---|
| Routing Engine | OSRM, OpenTripPlanner (OTP), Docker |
| Frontend | HTML, Vanilla CSS, JavaScript, Leaflet.js |
| Simulation | Python 3, `requests` |
| APIs | GraphQL (OTP), REST (OSRM) |
| Data Storage | JSON, CSV |

## Data & Configuration

- **`data/postcodes_attica.json`**: Local geocoding fallback mapping 272 Attica postal codes to coordinates.
- **`data/students_exam_dataset.csv`**: Sample dataset of 200 students, including `TK_KATOIKIA` (Origin Postal Code), `GRADE`, and `COURSE`.
- **`config/config.json`**: Configuration for the MNL model, simulation parameters, and policy scenarios.

## Requirements

- Python 3.8+
- Docker & Docker Desktop (for local OSRM routing)
- Git

## Getting Started

### 1. Clone the repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Start the OSRM Docker Containers

Start the vehicle routing engine (Port 5000):
```bash
docker run -d --name osrm_transit -p 5000:5000 -v "${PWD}/osrm_data/car:/data" osrm/osrm-backend osrm-routed --algorithm mld /data/attica.osrm
```

Start the pedestrian routing engine (Port 5001):
```bash
docker run -d --name osrm_foot -p 5001:5000 -v "${PWD}/osrm_data/foot:/data" osrm/osrm-backend osrm-routed --algorithm mld /data/attica.osrm
```

### 3. Start the OpenTripPlanner Container

The OTP container requires the `otp-data` folder, which contains the GTFS feeds for OSY (buses) and STASY (metro/tram), along with the OpenStreetMap data. When it boots up, it will build a graph in memory.
```bash
docker run -d -p 8080:8080 --name otp -v "${PWD}/otp-data:/var/otp" docker.io/opentripplanner/opentripplanner:latest --load --serve /var/otp
```

> **Note**: On Linux/macOS, replace `${PWD}` with `$(pwd)`.

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Web Dashboard
Open `frontend/index.html` in your web browser. Select an origin postal code and a destination campus to view the calculated routes, modal split, and CO2 emissions dynamically. 

### Python Simulation
Run the Monte Carlo simulation to process the student dataset:

```bash
python src/simulate_failing_students_co2.py
```

This will output a detailed report of the simulated trips and the total environmental footprint to the console. 

> **Fallback Mechanism**: If the OSRM Docker containers are not running, both the web app and the Python script will automatically fall back to using Haversine straight-line distance approximations to calculate the routes.
