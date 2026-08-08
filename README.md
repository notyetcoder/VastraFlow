# VastraFlaw

A comprehensive, marketplace-ready Frappe application designed to streamline apparel and garment manufacturing operations. 

## Overview

VastraFlaw extends the core capabilities of the Frappe ecosystem by introducing specialized modules tailored for the apparel industry[cite: 2]. It seamlessly integrates a dynamic Bill of Materials (BOM) engine, a centralized order book, and configurable matrix-based sizing and pricing logic[cite: 2].

## Key Features

* **Apparel Core:** Centralized management for complex sales orders, custom size matrices, and specialized price lists[cite: 2].
* **Dynamic BOM Engine:** Automated, intelligent Bill of Materials generation featuring customizable strategies (Auto-Generate, Bypass, and Match Existing)[cite: 2].
* **Order Book Management:** A streamlined dashboard and tracking system for production orders and fulfillment operations[cite: 2].
* **Production Job Cards:** Custom HTML and JSON print formats optimized for clear, actionable shop floor execution[cite: 2].

## Installation

From your Frappe bench directory, execute the following commands to fetch and install the application on your site:

```bash
# Fetch the app from the repository
bench get-app [https://github.com/notyetcoder/VastraFlow.git](https://github.com/notyetcoder/VastraFlow.git)

# Install the app on your specific site
bench --site your-site-name install-app vastraflaw

# Run database migrations
bench --site your-site-name migrate

# Rebuild assets
bench build --app vastraflaw