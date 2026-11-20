# BusBidder Spain - experiment results

Produced by `python main.py experiments`. The data and the ranking are deterministic, so running the command again gives the same results.

## E1 Same offers, different travellers

All profiles search Madrid to Malaga, 12-14 July, among the same 743 valid offers (final hybrid scoring).

| Profile | Acceptable offers | Rank 1 | Total | Lead over rank 2 | Rank 2 |
|---|---|---|---|---|---|
| Budget traveller | 6 | SOL-MAL-0714-01 (SolRuta, 14/07 09:30, EUR 30.00, fixed fare) | 74.6 | 11.8 | SOL-MAL-0712-01 (SolRuta, 12/07 14:00, EUR 32.50, changeable fare) |
| Business traveller | 6 | CST-MAL-0713-01 (CostaLink, 13/07 11:00, EUR 44.00, changeable fare) | 56.5 | 1.5 | CAM-MAL-0712-01 (Camino Express, 12/07 18:00, EUR 66.00, changeable and refundable fare) |
| Flexibility-focused tourist | 7 | VRD-MAL-0713-01 (VerdeBus, 13/07 14:30, EUR 47.00, changeable and refundable fare) | 77.8 | 7.0 | VRD-MAL-0712-09 (VerdeBus, 12/07 11:00, EUR 45.50, changeable and refundable fare) |

## E2 First scoring version (min-max for all criteria) compared with the final version

Final version: min-max for price and duration; fixed scales for departure (100 at the preferred time, 0 at 6 hours away) and flexibility (0 / 60 / 100).

| Profile | Rank 1 with min-max for all | Rank 1 final | Winner changed | Offers that changed position |
|---|---|---|---|---|
| Budget traveller | SOL-MAL-0714-01 (SolRuta, 14/07 09:30, EUR 30.00, fixed fare) | SOL-MAL-0714-01 (SolRuta, 14/07 09:30, EUR 30.00, fixed fare) | no | 0 of 6 |
| Business traveller | VRD-MAL-0712-09 (VerdeBus, 12/07 11:00, EUR 45.50, changeable and refundable fare) | CST-MAL-0713-01 (CostaLink, 13/07 11:00, EUR 44.00, changeable fare) | yes | 6 of 6 |
| Flexibility-focused tourist | VRD-MAL-0713-01 (VerdeBus, 13/07 14:30, EUR 47.00, changeable and refundable fare) | VRD-MAL-0713-01 (VerdeBus, 13/07 14:30, EUR 47.00, changeable and refundable fare) | no | 2 of 7 |

## E3 Weight sensitivity

Each weight is moved up or down in steps of 1 percentage point; the other weights are scaled so the total stays 100 %. The table shows the smallest change that gives a different rank-1 offer ("-" = no change within the allowed range).

### Budget traveller (rank 1: SOL-MAL-0714-01)

| Criterion | Weight | Smallest increase that changes rank 1 | Smallest decrease that changes rank 1 |
|---|---|---|---|
| Price | 60 % | +40 points -> NOC-MAL-0712-01 | -30 points -> SOL-MAL-0713-01 |
| Duration | 15 % | +29 points -> SOL-MAL-0712-01 | - |
| Departure convenience | 10 % | - | - |
| Flexibility | 15 % | +14 points -> SOL-MAL-0712-01 | - |

### Business traveller (rank 1: CST-MAL-0713-01)

| Criterion | Weight | Smallest increase that changes rank 1 | Smallest decrease that changes rank 1 |
|---|---|---|---|
| Price | 10 % | +11 points -> SOL-MAL-0713-01 | -2 points -> CAM-MAL-0712-01 |
| Duration | 40 % | +2 points -> CAM-MAL-0712-01 | -3 points -> SOL-MAL-0713-01 |
| Departure convenience | 35 % | +4 points -> SOL-MAL-0713-01 | -2 points -> CAM-MAL-0712-01 |
| Flexibility | 15 % | +4 points -> CAM-MAL-0712-01 | - |

### Flexibility-focused tourist (rank 1: VRD-MAL-0713-01)

| Criterion | Weight | Smallest increase that changes rank 1 | Smallest decrease that changes rank 1 |
|---|---|---|---|
| Price | 25 % | +10 points -> SOL-MAL-0712-01 | - |
| Duration | 15 % | +85 points -> CST-MAL-0713-01 | -13 points -> SOL-MAL-0712-01 |
| Departure convenience | 10 % | +55 points -> SOL-MAL-0712-01 | - |
| Flexibility | 50 % | +50 points -> VRD-MAL-0712-09 | -24 points -> SOL-MAL-0712-01 |

## E4 Extreme value

An artificial offer (EUR 12.00, 14 hours, otherwise like SOL-MAL-0714-01) is added for the budget traveller. It ranks 1 of 7. The other offers' min-max scores change although they themselves did not change.

| Offer | Price | Price score before | Price score after | Duration score before | Duration score after | Rank before | Rank after |
|---|---|---|---|---|---|---|---|
| SOL-MAL-0714-01 | 30.00 | 100 | 33 | 36 | 82 | 1 | 2 |
| SOL-MAL-0712-01 | 32.50 | 72 | 24 | 59 | 88 | 2 | 3 |
| NOC-MAL-0712-01 | 30.00 | 100 | 33 | 18 | 77 | 3 | 5 |
| NOC-MAL-0713-01 | 31.50 | 83 | 28 | 9 | 74 | 4 | 6 |
| SOL-MAL-0713-01 | 39.00 | 0 | 0 | 100 | 100 | 5 | 4 |
| NOC-MAL-0714-02 | 35.00 | 44 | 15 | 0 | 71 | 6 | 7 |

## E5 Effective influence of each criterion

For each criterion: the spread (highest minus lowest) of the points it adds to the total among the acceptable offers, and its share of all spreads. A criterion with a large weight but a small spread hardly affects the order.

### Budget traveller

| Criterion | Weight | Spread of points | Share of influence |
|---|---|---|---|
| Price | 60 % | 60.0 | 64 % |
| Duration | 15 % | 15.0 | 16 % |
| Departure convenience | 10 % | 9.2 | 10 % |
| Flexibility | 15 % | 9.0 | 10 % |

### Business traveller

| Criterion | Weight | Spread of points | Share of influence |
|---|---|---|---|
| Price | 10 % | 10.0 | 11 % |
| Duration | 40 % | 40.0 | 44 % |
| Departure convenience | 35 % | 35.0 | 38 % |
| Flexibility | 15 % | 6.0 | 7 % |

### Flexibility-focused tourist

| Criterion | Weight | Spread of points | Share of influence |
|---|---|---|---|
| Price | 25 % | 25.0 | 36 % |
| Duration | 15 % | 15.0 | 21 % |
| Departure convenience | 10 % | 10.0 | 14 % |
| Flexibility | 50 % | 20.0 | 29 % |

## E6 Data validation

Valid offers loaded: 743. Rows set aside for review: 14 (problems: 15). Automatic corrections: 2. Valid but sold-out offers: 42 (kept, removed later by the seat constraint).

| Field with a problem | Number of problems |
|---|---|
| arrival | 2 |
| changeable | 1 |
| company_id | 1 |
| departure | 1 |
| destination_id | 1 |
| offer_id | 2 |
| price_eur | 2 |
| rating | 1 |
| refundable | 1 |
| row | 1 |
| seats_available | 1 |
| transfers | 1 |
