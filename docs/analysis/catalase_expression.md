# Catalase Gene Expression in Alteromonas

## Catalase genes in the KG

All catalase genes in the knowledge graph belong to *Alteromonas macleodii* — none are found in *Prochlorococcus*, consistent with the known absence of catalase in that genus.

| Gene | Product | Strains | Ortholog cluster |
|------|---------|---------|------------------|
| **katA** | catalase | MIT1002, HOT1A3, EZ55 | 464SN@72275 |
| **katB** | catalase | MIT1002, HOT1A3, EZ55 | 4644E@72275 |
| **katG** | catalase/peroxidase HPI | MIT1002, HOT1A3, EZ55 | 4641A@72275 |
| — | catalase family protein | EZ55 only | no cluster |

katG is a bifunctional enzyme with both catalase and broad-spectrum peroxidase activity. The uncharacterized catalase family protein (EZ55_02907) has no expression data.

## Expression by study

### Nutrient starvation in HOT1A3 (doi:10.1101/2025.11.24.690089)

Long-term nutrient starvation (PRO99-lowN) in *Alteromonas macleodii* HOT1A3, both axenic and in coculture with *Prochlorococcus* MED4.

**Starvation strongly downregulates all three catalases**, with katB showing the largest effect:

| Gene | Context | Time point | log2FC | padj |
|------|---------|------------|--------|------|
| katB | axenic | day 31 | -9.8 | 8e-16 |
| katA | axenic | day 31 | -7.8 | 2e-11 |
| katB | coculture w/ MED4 | day 31 | -7.7 | 3e-10 |
| katA | coculture w/ MED4 | day 31 | -6.8 | 2e-9 |
| katG | axenic | day 31 | -5.4 | 7e-9 |
| katA | axenic | day 18 | -4.3 | 4e-4 |
| katB | axenic | day 18 | -4.1 | 0.002 |
| katG | axenic | days 60+89 | -3.6 | 3e-6 |
| katG | axenic | day 18 | -3.3 | 6e-4 |
| katG | coculture w/ MED4 | day 31 | -3.1 | 0.001 |
| katA | axenic | days 60+89 | -2.9 | 0.003 |
| katB | axenic | days 60+89 | -2.7 | 0.013 |

**Coculture with MED4 (vs axenic, no starvation)** also downregulates all three catalases at day 11:

| Gene | log2FC | padj |
|------|--------|------|
| katA | -3.5 | 0.015 |
| katB | -3.2 | 0.050 |
| katG | -2.9 | 0.010 |

**Late-starvation recovery in coculture**: At days 60-89 in coculture with MED4, katA and katG show significant upregulation relative to exponential phase, suggesting partial recovery of ROS defense when Prochlorococcus is present:

| Gene | Time point | log2FC | padj |
|------|------------|--------|------|
| katA | day 89 | +1.8 | 6e-6 |
| katA | days 60+89 | +1.6 | 6e-6 |
| katG | day 89 | +1.3 | 3e-4 |
| katG | days 60+89 | +1.1 | 5e-4 |

### MIT1002 coculture with NATL2A (doi:10.1038/ismej.2016.82)

Time-course of *Alteromonas* MIT1002 in coculture with *Prochlorococcus* NATL2A.

All three catalases are upregulated at 24-48h post-inoculation:

| Gene | Time point | log2FC |
|------|------------|--------|
| katA | 24h vs 12h | +2.7 |
| katA | 48h vs 12h | +2.3 |
| katB | 48h vs 12h | +2.2 |
| katB | 24h vs 12h | +1.9 |
| katG | 24h vs 12h | +1.4 |

No adjusted p-values reported in this dataset. The upregulation is consistent with Alteromonas responding to photosynthetically-derived ROS from Prochlorococcus.

### EZ55 coculture with cyanobacteria at different CO2 levels (doi:10.1038/s43705-022-00197-2)

*Alteromonas macleodii* EZ55 cocultured with different cyanobacterial partners (MIT9312, WH8102, CC9311) at ambient (400 ppm) and elevated (800 ppm) CO2.

**Partner- and CO2-dependent effects**:

| Gene | Partner | CO2 | log2FC | padj |
|------|---------|-----|--------|------|
| katB | WH8102 | 800 ppm | +2.4 | 4e-5 |
| katB | MIT9312 | 400 ppm | +2.3 | 4e-9 |
| katA | MIT9312 | 400 ppm | +2.2 | 4e-10 |
| katG | MIT9312 | 400 ppm | +1.9 | 3e-12 |
| katA | WH8102 | 800 ppm | +1.8 | 6e-4 |
| katB | MIT9312 | 800 ppm | -2.7 | 4e-6 |
| katA | MIT9312 | 800 ppm | -2.0 | 2e-4 |
| katA | CC9311 | 400 ppm | -1.7 | 7e-5 |
| katB | CC9311 | 400 ppm | -1.7 | 1e-4 |
| katG | WH8102 | 400 ppm | -1.0 | 8e-4 |

MIT9312 at ambient CO2 strongly upregulates all catalases, but at elevated CO2 the response reverses to downregulation. CC9311 coculture suppresses catalase at ambient CO2.

### EZ55 + MIT9312 elevated CO2 effect (doi:10.1038/ismej.2017.189)

Direct comparison of elevated (800 ppm) vs ambient (400 ppm) CO2 in EZ55 cocultured with MIT9312:

| Gene | log2FC | padj |
|------|--------|------|
| katB | -1.5 | 0.004 |
| katA | -1.4 | 0.015 |

Elevated CO2 downregulates catalase, consistent with reduced photorespiration and ROS production at high CO2.

### Dark-tolerant NATL2A coculture (doi:10.1093/ismeco/ycae131)

MIT1002 cocultured with dark-tolerant vs parental NATL2A under a 13:11 diel light:dark cycle. No significant changes in catalase expression (all padj = 1.0 or > 0.1). The dark-tolerance phenotype does not strongly affect catalase.

## Summary

1. **Nutrient starvation massively downregulates all three catalases** in Alteromonas HOT1A3, with katB showing the strongest response (up to ~1000-fold decrease). ROS defense is deprioritized under carbon/nitrogen limitation.

2. **Coculture with Prochlorococcus generally upregulates catalase** (NATL2A in MIT1002; MIT9312 in EZ55 at ambient CO2), likely reflecting a need to detoxify photosynthetically-derived H2O2.

3. **MED4 coculture is an exception** — it downregulates catalase in HOT1A3, potentially reflecting strain-specific interaction dynamics or reduced ROS exchange.

4. **CO2 modulates the coculture response**: elevated CO2 reverses MIT9312-induced catalase upregulation in EZ55 and independently downregulates katA/katB, consistent with reduced ROS under high CO2.

5. **Late-starvation recovery**: in coculture with MED4, katA and katG partially recover at days 60-89, suggesting Prochlorococcus-derived organic matter may sustain Alteromonas metabolism and ROS defense capacity during prolonged starvation.

---

## Review

Verified against the KG on 2025-03-15.

### Numbers check

All reported log2FC and padj values match the KG (rounded appropriately). No fabricated numbers.

### Issue 1: Gene inventory is incomplete — paralogs conflated

The document says "three catalases" but the KG has more:

| What the doc says | What the KG actually has |
|---|---|
| katA — one per strain | **Two katA copies per strain** (e.g. HOT1A3: ACZ81_02025 + ACZ81_11985, both in cluster 464SN) |
| katB — one per strain | katB exists, but MIT1002 also has **katE** (MIT1002_02513) in the same cluster (4644E) |
| katG — one per strain | Correct |
| — | Catalase family protein (EZ55_02907) — mentioned |

The two katA copies per strain behave completely differently (see below).

### Issue 2: Late-starvation "recovery" of katA conflates two paralogs

The document presents a coherent narrative: katA is massively downregulated by starvation, then partially recovers in late coculture. But these data come from **two different genes**:

- **ACZ81_02025** (katA copy 1): starvation at day 31 → log2FC -7.8 (padj 2e-11). Late coculture recovery? **No** — all late time points have padj > 0.5 (not significant).
- **ACZ81_11985** (katA copy 2): starvation → essentially unchanged (near-zero log2FC, non-significant). Late coculture at day 89 → log2FC +1.77 (padj 6e-6).

ACZ81_11985 was never suppressed by starvation. Its upregulation at day 89 is not a "recovery" but a distinct coculture response from a different paralog. **Summary point 5 is invalid as written.**

### Issue 3: katB vs katE misattribution in MIT1002 NATL2A coculture

The NATL2A coculture section reports "katB" at +2.2 (48h) and +1.9 (24h). These values come from **MIT1002_02513 (katE)**, not MIT1002_03530 (katB). MIT1002_03530 has no NATL2A coculture expression data in the KG. They share ortholog cluster 4644E but are distinct genes.

### Issue 4: Statistical concerns

1. **MIT1002 NATL2A coculture** — no adjusted p-values in the dataset. The document notes this but then draws firm conclusions ("consistent with Alteromonas responding to photosynthetically-derived ROS"). These are fold-change estimates only, without statistical validation.

2. **katB MED4 coculture** — padj = 0.050, exactly at the conventional significance threshold. Not flagged as borderline.

3. **Duplicate KG entries for katG** — ACZ81_16125 at day 89 in coculture has two entries: +1.26 (padj 3e-4) and -1.16 (padj 0.29). The document reports only the significant one. These likely reflect different contrasts in the underlying DESeq2 analysis but the ambiguity is not addressed.

4. **No correction for multiple comparisons** across genes, conditions, and studies. Each p-value is taken at face value from its original study.

5. **"~1000-fold decrease"** for katB: 2^9.8 = 891, approximately correct but is a point estimate from a single condition/time point.

### What holds up

- Starvation downregulation of ACZ81_02025 (katA-1), ACZ81_16915 (katB), ACZ81_16125 (katG) — large effects, highly significant.
- EZ55 CO2 studies — values match the KG, interpretation is sound.
- MED4 coculture downregulation — real, though katB is borderline (padj = 0.050).
- Dark-tolerant NATL2A section — correctly reports no significant changes.

---

## Updated gene inventory

All catalase genes in the KG, disambiguated by locus tag:

| Gene name | Locus tag | Product | Strain | Ortholog cluster |
|-----------|-----------|---------|--------|------------------|
| katA | ACZ81_02025 | catalase | HOT1A3 | 464SN@72275 |
| katA | ACZ81_11985 | catalase | HOT1A3 | 464SN@72275 |
| katA | MIT1002_02464 | catalase | MIT1002 | 464SN@72275 |
| katA | MIT1002_00461 | catalase | MIT1002 | 464SN@72275 |
| katA | EZ55_00433 | catalase | EZ55 | 464SN@72275 |
| katA | EZ55_02459 | catalase | EZ55 | 464SN@72275 |
| katB | ACZ81_16915 | catalase | HOT1A3 | 4644E@72275 |
| katB | MIT1002_03530 | catalase | MIT1002 | 4644E@72275 |
| katB | EZ55_03522 | catalase | EZ55 | 4644E@72275 |
| katE | MIT1002_02513 | catalase | MIT1002 | 4644E@72275 |
| katG | ACZ81_16125 | catalase/peroxidase HPI | HOT1A3 | 4641A@72275 |
| katG | MIT1002_03345 | catalase/peroxidase HPI | MIT1002 | 4641A@72275 |
| katG | EZ55_03362 | catalase/peroxidase HPI | EZ55 | 4641A@72275 |
| — | EZ55_02907 | catalase family protein | EZ55 | — |

Each strain carries two katA paralogs in the same ortholog cluster. MIT1002 additionally carries katE in the katB cluster (4644E). The two katA copies show dramatically different expression behavior (see below).

---

## Updated analysis

### Starvation response in HOT1A3 — paralog-resolved

The starvation downregulation story holds for one katA copy but not the other:

| Locus tag | Gene | Day 31 axenic log2FC | padj | Day 31 coculture log2FC | padj |
|-----------|------|---------------------|------|------------------------|------|
| ACZ81_02025 | katA-1 | -7.8 | 2e-11 | -6.8 | 2e-9 |
| ACZ81_11985 | katA-2 | +1.0 | 0.018 | +1.5 | 6e-5 |
| ACZ81_16915 | katB | -9.8 | 8e-16 | -7.7 | 3e-10 |
| ACZ81_16125 | katG | -5.4 | 7e-9 | -3.1 | 0.001 |

katA-1, katB, and katG are co-downregulated under starvation. katA-2 is not — it is mildly *upregulated*, especially in coculture. These two katA paralogs have opposite starvation responses despite sharing a gene name and ortholog cluster.

### Late time points in coculture — no recovery of starvation-suppressed genes

At days 60-89 in coculture with MED4:

| Locus tag | Gene | Time point | log2FC | padj | Interpretation |
|-----------|------|------------|--------|------|----------------|
| ACZ81_02025 | katA-1 | day 89 | +0.1 | 0.95 | Not significant — no recovery |
| ACZ81_02025 | katA-1 | days 60+89 | +0.6 | 0.64 | Not significant — no recovery |
| ACZ81_11985 | katA-2 | day 89 | +1.8 | 6e-6 | Significant, but this gene was never suppressed |
| ACZ81_11985 | katA-2 | days 60+89 | +1.6 | 6e-6 | Significant, but this gene was never suppressed |
| ACZ81_16125 | katG | day 89 | +1.3 | 3e-4 | Significant upregulation |
| ACZ81_16125 | katG | days 60+89 | +1.1 | 5e-4 | Significant upregulation |

katG does show genuine late upregulation in coculture (it was downregulated at day 31, then upregulated by day 89). However, the KG also contains a second entry for katG at day 89 in coculture showing log2FC -1.16, padj 0.29 — the two entries may reflect different contrasts and should be investigated.

For katA, the "recovery" signal comes entirely from the paralog (katA-2) that was never suppressed. The starvation-responsive paralog (katA-1) shows no significant change at late time points.

### MIT1002 NATL2A coculture — corrected gene assignments

| Locus tag | Gene | Time point | log2FC | padj |
|-----------|------|------------|--------|------|
| MIT1002_02464 | katA | 24h vs 12h | +2.7 | — |
| MIT1002_02464 | katA | 48h vs 12h | +2.3 | — |
| MIT1002_02513 | **katE** (not katB) | 48h vs 12h | +2.2 | — |
| MIT1002_02513 | **katE** (not katB) | 24h vs 12h | +1.9 | — |
| MIT1002_03345 | katG | 24h vs 12h | +1.4 | — |
| MIT1002_03345 | katG | 48h vs 12h | +0.8 | — |

No adjusted p-values are available for this dataset. katB (MIT1002_03530) has no expression data from this study.

### EZ55 CO2 studies — no corrections needed

The EZ55 data is correctly reported and interpreted. All values match the KG, genes are unambiguous (one katA/katB/katG per strain in this context, using EZ55_00433/EZ55_03522/EZ55_03362).

---

## Updated summary

1. **Nutrient starvation downregulates katA-1, katB, and katG** in HOT1A3, with katB showing the strongest response (log2FC -9.8, ~900-fold). The second katA paralog (katA-2, ACZ81_11985) is *not* suppressed by starvation and shows mild upregulation, especially in coculture.

2. **Coculture with Prochlorococcus generally upregulates catalase**: katA and katE are upregulated in MIT1002 + NATL2A; katA, katB, and katG are upregulated in EZ55 + MIT9312 at ambient CO2. However, the MIT1002 data lacks statistical testing (no padj values).

3. **MED4 coculture downregulates catalase** in HOT1A3 at day 11 — katA-1 (padj 0.015) and katG (padj 0.010) are significant; katB is borderline (padj = 0.050).

4. **CO2 modulates the coculture response**: elevated CO2 reverses MIT9312-induced upregulation in EZ55 and independently suppresses katA/katB. This is the best-supported finding — strong effect sizes, highly significant, consistent across two independent studies.

5. **No evidence of starvation recovery for katA**: the previously reported "late recovery" conflated two paralogs. The starvation-responsive katA-1 (ACZ81_02025) does not recover. katG (ACZ81_16125) does show significant upregulation at days 60-89 in coculture, but conflicting KG entries for the same time point warrant caution.

6. **The catalase gene family is larger than initially presented**: each Alteromonas strain carries two katA paralogs with divergent expression, and MIT1002 has a katE that was misidentified as katB. Future analyses should use locus tags, not gene names, to avoid paralog conflation.
