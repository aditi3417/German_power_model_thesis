# Unplanned outage modeling 

## Description

This project builds a predictive model for unplanned outages of German thermal power generation units, covering hard coal, lignite, and natural gas plants over the period 2015–2024.

The dataset is sourced from the [Zenodo repository](https://zenodo.org/records/15204429) published by Fusar Bassini (2025), which provides hourly time series of available and unavailable capacity for 384 generation units, constructed from outage reports on the ENTSO-E and EEX Transparency Platforms.

The goal is to train a model that predicts whether a unit will experience an outage in a given time window, using historical availability patterns alongside external features such as weather (temperature,precipitation) 
and grid load. Weather data is sourced from NOAA's Climate Data Online (CDO) Daily Summaries.

This work is inspired by the paper *"Seasonal and Weather Influences in the Outages of German Thermal Generators"* (Fusar Bassini et al., 2025).

---
