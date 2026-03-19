# 🚀 SurakshaPay – AI-Powered Parametric Income Protection for Gig Workers

---

## 📌 1. Problem Context

India’s gig economy is powered by millions of delivery partners working for platforms such as Zomato and Swiggy. These workers rely on consistent daily earnings to support their livelihoods. However, their income is highly vulnerable to external disruptions such as heavy rainfall, extreme heat, air pollution, and sudden curfews.

During such events, delivery partners are either unable to work or experience a sharp drop in order volume. This leads to immediate income loss, often reducing earnings by 20–30%. Unlike traditional salaried employees, gig workers do not have any structured safety net to absorb such shocks.

The core challenge is to design an insurance solution that:
- Focuses strictly on *loss of income (not health, accident, or vehicle damage)*
- Works on a *weekly pricing model*, aligned with gig workers’ earning cycles
- Uses *automation and AI* to eliminate manual claims and delays

---

## 💡 2. Solution Overview

SurakshaPay is a *mobile-first, AI-powered parametric insurance platform* that provides instant income protection to gig workers.

The system continuously monitors:
- Environmental conditions (rainfall, temperature, AQI)
- Social disruptions (curfews, strikes)
- Worker activity (deliveries, active hours)

When a disruption causes a measurable drop in income, SurakshaPay automatically:
1. Detects the event
2. Verifies the user’s activity and location
3. Calculates income loss
4. Triggers an instant payout via UPI

This removes the need for manual claim filing and ensures a *zero-touch, real-time insurance experience*.

---

## 🎯 3. Target Persona

The primary users of SurakshaPay are *food delivery partners working with platforms like Swiggy and Zomato*.

These workers are ideal for this solution because:
- They work outdoors and are highly exposed to environmental risks
- Their income is directly dependent on daily activity
- They operate on short financial cycles (daily/weekly)

---

## 👤 4. Persona-Based Scenario

Consider Ravi, a delivery partner in Chennai.

Ravi typically works 6 days a week and earns around ₹800 per day. On a normal day, he completes deliveries during peak hours such as lunch and dinner.

On a day of heavy rainfall:
- Road conditions become unsafe
- Customer demand drops
- Ravi is only able to work for 2 hours instead of 8

As a result, his earnings drop to ₹300.

The SurakshaPay system detects:
- Rainfall exceeding the defined threshold
- A drop in delivery activity greater than 40%
- GPS confirmation that Ravi is in the affected zone

Based on these conditions, the system automatically calculates his income loss and transfers ₹400 to his UPI account within minutes.

---

## 🔄 5. End-to-End System Workflow

The SurakshaPay system operates as a continuous automated pipeline:

### Step 1: Onboarding
The user registers using a mobile number and OTP. They select their delivery platform, enable GPS tracking, and link their UPI account for payouts.

### Step 2: Data Collection
The system continuously collects:
- Weather data (rainfall, temperature)
- Air quality data (AQI)
- Location data (GPS)
- Delivery activity (orders, active hours)

### Step 3: Risk Profiling
AI models analyze historical and real-time data to determine the user’s risk level based on:
- Location vulnerability
- Frequency of disruptions
- Work consistency
- Income variability

### Step 4: Policy Selection
The user selects a weekly insurance plan based on their risk level and desired coverage.

### Step 5: Real-Time Monitoring
The system continuously monitors:
- External disruptions
- User activity levels

### Step 6: Trigger Detection
If a disruption occurs and income drops beyond a threshold, the system activates the parametric trigger.

### Step 7: Claim Automation
The system:
- Validates the user’s location
- Verifies activity drop
- Runs fraud checks
- Calculates payout

### Step 8: Instant Payout
The payout is transferred via UPI within minutes.

---

## 💰 6. Weekly Pricing Model

SurakshaPay uses a *weekly subscription-based insurance model*.

Instead of paying large annual premiums, users pay a small fixed amount every week to stay protected during that period.

### Plan Structure:

| Plan     | Weekly Premium | Coverage |
|----------|---------------|----------|
| Basic    | ₹20           | ₹1000    |
| Standard | ₹35           | ₹1500    |
| Pro      | ₹50           | ₹2500    |

### Key Concepts:

- *Premium* is the amount paid weekly to remain insured
- *Coverage* is the maximum amount the user can receive in a week

This model ensures:
- Affordability for gig workers
- Alignment with weekly earning cycles
- Predictable cost structure

---

## 🧠 7. AI-Based Pricing (Detailed Explanation)

AI is used to ensure *fair and personalized pricing* instead of charging all users the same premium.

### Problem Without AI:
All users pay the same price regardless of risk, which is unfair and unsustainable.

### AI-Based Approach:
The system calculates a risk score using factors such as:
- Location risk (flood-prone or pollution-heavy areas)
- Weather volatility
- Work consistency
- Historical income fluctuations

### Pricing Function:
#Premium = Base Price + Risk Adjustment

Where:
- Risk Adjustment is computed using ML models

### Example:
- Low-risk worker → ₹20–₹25
- Medium-risk worker → ₹35
- High-risk worker → ₹50+

This ensures:
- High-risk users contribute slightly more
- Low-risk users are rewarded with lower premiums

---

## 🌪️ 8. Parametric Trigger System

SurakshaPay uses *parametric triggers*, meaning payouts are based on measurable external conditions rather than manual claims.

### Trigger Categories:

#### Environmental Triggers:
- Rainfall > 50mm
- Temperature > 40°C
- AQI > 300

#### Social Triggers:
- Curfews
- Strikes
- Road closures

#### Income Trigger:
- Delivery activity drop > 40%

### Trigger Logic:
##IF (External Disruption Detected) AND (Income Drop > Threshold)
##→ Payout Triggered

This ensures that payouts are strictly linked to *loss of income caused by external disruptions*.

---

## 📊 9. Income Loss Detection Logic

The system builds a *personalized income baseline* for each user.

### Step 1: Baseline Calculation
### Expected Income = Average of last 7 days

### Step 2: Real-Time Comparison
### Drop % = (Expected - Actual) / Expected


### Step 3: Decision
- If Drop > 40% → valid income loss

This approach ensures accuracy and personalization.

---

## ⚡ 10. Automated Claim & Payout System

SurakshaPay eliminates manual claims completely.

### Flow:
1. Detect disruption
2. Validate location
3. Verify income drop
4. Run fraud checks
5. Calculate payout
6. Transfer via UPI

### Processing Time:
*Less than 5 minutes*

---

## 🛡️ 11. Fraud Detection System

To ensure reliability, the system includes multiple fraud detection layers:

- *GPS Validation:* Ensures user is in affected zone
- *Anomaly Detection:* Identifies unusual inactivity
- *Duplicate Claim Prevention:* Blocks repeated claims
- *Behavioral Analysis:* Compares past and current activity

---

## 📱 12. Platform Choice

A mobile-first approach is chosen because:
- Gig workers primarily use smartphones
- Real-time tracking requires device-level integration
- Instant payouts and notifications are mobile-centric

---

## 🔌 13. System Integrations

- Weather API (OpenWeatherMap)
- AQI API
- Google Maps API
- Payment Gateway (UPI / Razorpay sandbox)
- Delivery platform APIs (simulated)

---

## 📊 14. Analytics Dashboard

### Worker Dashboard:
- Earnings protected
- Claims received
- Active coverage

### Admin Dashboard:
- Risk heatmaps
- Claim trends
- Fraud alerts

---

## 💡 15. Key Innovations

- Micro-zone level risk pricing
- AI-based personalized income prediction
- Fully automated zero-claim insurance model
- Gamified premium reduction for consistent workers

---

## 🧱 16. Tech Stack

- Frontend: React + Tailwind CSS  
- Backend: FastAPI  
- AI/ML: Python (scikit-learn)  
- Database: PostgreSQL / MongoDB  

---

## 🏗️ 17. System Architecture




## 📌 19. Conclusion

SurakshaPay redefines insurance for gig workers by combining AI, real-time data, and parametric triggers to create a seamless income protection system.

By focusing on affordability, automation, and personalization, the platform provides a scalable and practical solution for income instability in the gig economy.
