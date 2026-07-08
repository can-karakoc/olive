# Ground Truth Label Data - Provenance

This document tracks the sources, processing steps, and quality of ground truth production data used to train yield estimation models.

## Data Sources

### TÜİK (Turkish Statistical Institute)
**Official Name:** Türkiye İstatistik Kurumu  
**Website:** https://www.tuik.gov.tr/  
**Dataset:** Bitkisel Ürün İstatistikleri (Plant Production Statistics)

**Access:**
- Public data portal: https://biruni.tuik.gov.tr/medas/
- API: Available for bulk download
- Format: Excel, CSV

**Coverage:**
- Geographic: Province-level (NUTS-3)
- Temporal: Annual (harvest year)
- Products: Olive (fruit), Olive oil (production)

**Data Quality:**
- Official government statistics
- Based on farmer surveys + agricultural census
- Published with ~6-12 month lag after harvest

**Last Accessed:** TBD

---

### UZZK (National Olive and Olive Oil Council)
**Official Name:** Ulusal Zeytin ve Zeytinyağı Konseyi  
**Website:** https://www.uzzk.org/  

**Dataset:** Harvest estimates and production forecasts

**Access:**
- Annual reports (PDF)
- Press releases during harvest season
- Industry bulletins

**Coverage:**
- Geographic: Regional + national totals
- Temporal: Harvest season estimates (updated monthly Oct-Feb)
- Products: Table olives vs. oil olives (separated)

**Data Quality:**
- Industry-validated estimates
- More timely than TÜİK (real-time during harvest)
- May be revised post-season

**Last Accessed:** TBD

---

### IOC (International Olive Council)
**Official Name:** International Olive Council  
**Website:** https://www.internationaloliveoil.org/  

**Dataset:** World Olive Oil Figures

**Access:**
- Public data portal: https://www.internationaloliveoil.org/what-we-do/economic-affairs-promotion-unit/
- Format: Excel, PDF reports

**Coverage:**
- Geographic: Country-level (Turkey)
- Temporal: Marketing year (Oct-Sep)
- Products: Olive oil production, table olive production, consumption, trade

**Data Quality:**
- Harmonized international statistics
- Useful for global context and price drivers
- Turkey data sourced from TÜİK/UZZK

**Last Accessed:** TBD

---

## Data Files

### `turkey_olive_production.csv`
**Status:** 🔴 To be collected  
**Description:** Provincial olive fruit production (tonnes)  
**Schema:**
```
province,year,production_tonnes,on_off_year,source,notes
İzmir,2023,450000,on,TUIK,
Aydın,2023,320000,on,TUIK,
...
```

**Target Coverage:**
- Years: 2018-2024 (minimum 6 seasons to span 3 on/off cycles)
- Provinces: Aegean (İzmir, Aydın, Balıkesir, Manisa, Muğla) at minimum
- Additional regions: Marmara, Mediterranean, SE Anatolia (if available)

---

### `turkey_olive_oil_production.csv`
**Status:** 🔴 To be collected  
**Description:** Provincial/regional olive oil production (tonnes)  
**Schema:**
```
region,province,year,oil_production_tonnes,on_off_year,source,notes
Aegean,İzmir,2023,85000,on,TUIK,
Aegean,Aydın,2023,62000,on,TUIK,
...
```

**Notes:**
- TÜİK may only provide province-level fruit production, not oil
- Oil yield calculation: ~18-22% oil extraction rate from fruit
- Separate oil vs. table olive destinations by region (see brief)

---

### `on_off_year_cycle.csv`
**Status:** 🟡 Partial (from brief)  
**Description:** Documented on/off year classifications  
**Schema:**
```
year,classification,national_production_tonnes,source,notes
2024,on,505000,IOC,High production year
2025,off,290000,IOC (forecast),Expected 43% drop - normal cycle
2023,on,480000,IOC,
2022,off,275000,IOC,
...
```

**Known data points (from brief):**
- 2024/25: On-year, ~505k tonnes oil
- 2025/26: Off-year, ~290k tonnes oil (forecast)

---

## Data Processing Steps

1. **Collection:**
   - Manual download from TÜİK portal (MEDAS)
   - UZZK reports scraped from PDFs
   - IOC Excel data downloaded

2. **Standardization:**
   - Province names normalized (Turkish characters preserved)
   - Years converted to harvest year (if marketing year used)
   - Units standardized to tonnes
   - On/off year flag added (from historical pattern + literature)

3. **Quality Checks:**
   - Cross-validate TÜİK vs UZZK vs IOC (should agree within 10%)
   - Flag anomalies (e.g., >50% YoY change that isn't on/off cycle)
   - Check for missing provinces or years

4. **Versioning:**
   - Each update creates new dated file: `turkey_olive_production_v2_20260708.csv`
   - Git tracks changes
   - This PROVENANCE.md updated with change log

---

## Known Issues & Limitations

### 1. Province-level granularity constraint
**Issue:** TÜİK data is province-level (NUTS-3), not parcel-level  
**Impact:** Cannot train pixel-level yield models; limited to province aggregation  
**Mitigation:** Accepted constraint; MVP models province-level only

### 2. On/off year classification uncertainty
**Issue:** Official stats don't explicitly label on/off years  
**Impact:** Must infer from production pattern or literature  
**Mitigation:**
- Use multi-year average as baseline
- Flag years with >30% deviation as likely off-year
- Cross-check with UZZK reports (they mention cycle explicitly)

### 3. Oil vs. fruit production mismatch
**Issue:** TÜİK reports fruit (tonnes), but we care about oil (tonnes)  
**Impact:** Need conversion factor, which varies by region/year  
**Mitigation:**
- Use regional average oil extraction rate: 18-22%
- Aegean: ~20% (high quality oil production)
- Marmara: ~15% (more table olives)
- Cross-check with IOC national oil production totals

### 4. Temporal lag
**Issue:** TÜİK data published 6-12 months after harvest  
**Impact:** Cannot validate current-season nowcasts immediately  
**Mitigation:** Use UZZK real-time estimates during season; validate against TÜİK post-publication

### 5. Missing baseline for alternate bearing cycle
**Issue:** Need ≥6 years to span 3 full on/off cycles for robust training  
**Impact:** If <6 years available, model may misinterpret cycle as weather effect  
**Mitigation:**
- Target 2018-2024 (7 years) minimum
- Explicitly encode on/off year as feature (mandatory)
- Use IOC historical data for pre-2018 context if TÜİK unavailable

---

## Next Steps

1. **Immediate:**
   - [ ] Access TÜİK MEDAS portal, download 2018-2024 provincial olive production
   - [ ] Extract on/off year pattern from IOC World Olive Oil Figures reports
   - [ ] Create `turkey_olive_production.csv` with ≥6 years

2. **Short-term:**
   - [ ] Scrape UZZK annual reports for regional breakdowns
   - [ ] Validate TÜİK vs IOC national totals (should match within 5%)
   - [ ] Add province-to-region mapping (Aegean, Marmara, etc.)

3. **Long-term:**
   - [ ] Automate TÜİK API access for annual updates
   - [ ] Build web scraper for UZZK harvest reports
   - [ ] Establish data-sharing agreement with UZZK (if possible)

---

## References

- TÜİK Plant Production Statistics: https://www.tuik.gov.tr/en/subject-theme/statistics/plant-production.html
- UZZK Official Website: https://www.uzzk.org/
- IOC Economic Data: https://www.internationaloliveoil.org/what-we-do/economic-affairs-promotion-unit/
- Alternate Bearing in Olives (literature): Lavee et al., 2007; Fernández-Escobar et al., 2013

---

**Last Updated:** 2026-07-08  
**Status:** Initial template created; data collection pending
