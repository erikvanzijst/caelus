"""
Caelus Pricing Model — Interactive cost & pricing explorer.

Run:  uv run streamlit run pricing_model.py --server.address 0.0.0.0 --server.port 8501
"""

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Caelus Pricing Model", layout="wide")
st.title("Caelus Pricing Model")

# ─────────────────────────────────────────────────
# Sidebar: Cost model selection
# ─────────────────────────────────────────────────
st.sidebar.header("Cost Model")
cost_mode = st.sidebar.radio(
    "How to compute per-customer costs?",
    ["Server-share (recommended)", "Component-based"],
    help="**Server-share**: Define a reference server (e.g. Hetzner AX162-R) and compute "
    "each customer's cost as the fraction of that server they consume. More realistic.\n\n"
    "**Component-based**: Price CPU, RAM, storage, bandwidth independently. "
    "Useful for understanding cost structure but can be misleading for RAM/CPU "
    "since these are shared fixed resources on a server.",
)

# ─────────────────────────────────────────────────
# Sidebar: Server-share model inputs
# ─────────────────────────────────────────────────
if cost_mode == "Server-share (recommended)":
    st.sidebar.header("Reference Server")
    st.sidebar.caption(
        "Defaults match Caelus baseline hardware: 2x Xeon (48 cores total), "
        "256GB RAM, 2x 3.8TB NVMe. Similar spec to Hetzner AX162-R (€199/mo ≈ $215/mo)."
    )

    server_cost_mo = st.sidebar.number_input(
        "Server cost ($/month, all-in)",
        value=215.0,
        step=10.0,
        help="Monthly rental or amortised purchase+colo cost. "
        "Hetzner AX162-R: €199/mo ≈ $215. Includes power, bandwidth, colo.\n\n"
        "Other references:\n"
        "- Hetzner AX102 (16c, 128GB, 3.84TB): €109/mo ≈ $118\n"
        "- Hetzner EX130-R (24c Xeon, 256GB ECC, 3.84TB): €134/mo ≈ $145\n"
        "- OVH Advance-2 (8c EPYC, 64GB, 1.92TB): $173/mo\n"
        "- OVH RISE-L (16c Ryzen 9, 128GB, 960GB): $177/mo",
    )
    server_cpu_cores = st.sidebar.number_input(
        "Server CPU cores", value=48, min_value=1, step=1,
        help="Physical cores. EPYC 9454P = 48c. Xeon Gold 5412U = 24c. Ryzen 9 7950X3D = 16c.",
    )
    server_ram_gb = st.sidebar.number_input(
        "Server RAM (GB)", value=256, min_value=1, step=32,
        help="AX162-R: 256GB DDR5 ECC. AX102: 128GB. EX130-R: 256GB.",
    )
    st.sidebar.subheader("Storage (pooled across cluster)")
    st.sidebar.caption(
        "Storage is pooled across all servers in the cluster. "
        "Additional NVMe can be added independently of compute servers."
    )
    server_storage_tb = st.sidebar.number_input(
        "NVMe per server (TB)", value=7.60, step=0.5, format="%.2f",
        help="Baseline: 2x 3.8TB = 7.6TB raw per server.",
    )
    storage_usable_pct = st.sidebar.slider(
        "Usable storage after RAID/FS overhead (%)", min_value=50, max_value=100, value=80, step=5,
        help="ZFS mirror = 50%. RAID-1 = 50%. Single disk = ~95%. RAIDZ1 (3 disk) ≈ 67%.",
    )
    avg_storage_utilisation_pct = st.sidebar.slider(
        "Avg customer storage utilisation (%)", min_value=10, max_value=100, value=50, step=5,
        help="What percentage of their storage plan does the average customer actually use? "
        "Not every customer maxes out their quota. This lets you overcommit storage.\n\n"
        "Industry references:\n"
        "- Email providers: ~30-40%\n"
        "- Cloud storage (consumer): ~20-40%\n"
        "- Photo storage: ~40-60% (photos accumulate over time)\n"
        "- Password managers: ~10-20% (tiny vaults)\n\n"
        "At 50%, you can sell 2x more storage plans than you physically have.",
    )

    nvme_cost_tb_yr = st.sidebar.number_input(
        "NVMe cost ($/TB/year)",
        value=40.0,
        step=5.0,
        help="Amortised cost per TB per year for all storage (baseline + expansion).\n\n"
        "Research-based references (5yr amortisation, March 2026 prices):\n"
        "- Kioxia CM7-R 7.68TB: ~$147/TB → $29/TB/yr (best value)\n"
        "- Micron 7450 Pro 7.68TB: ~$174/TB → $35/TB/yr\n"
        "- Micron 7450 Pro 3.84TB: ~$190/TB → $38/TB/yr\n"
        "- Micron 7500 Pro 7.68TB: ~$312/TB → $62/TB/yr\n"
        "- Samsung PM9A3 3.84TB: ~$390/TB → $78/TB/yr (brand premium)\n\n"
        "⚠️ NAND prices have risen ~246% since Q1 2025 due to AI/HBM demand.",
    )

    st.sidebar.subheader("Bandwidth")
    server_bw_included_tb = st.sidebar.number_input(
        "Included bandwidth per server (TB/mo)", value=20.0, step=5.0,
        help="Hetzner includes 20TB+ on most plans. OVH: unmetered 1Gbps.",
    )
    extra_bw_cost_tb = st.sidebar.number_input(
        "Extra bandwidth cost ($/TB)", value=1.30, step=0.10, format="%.2f",
        help="Hetzner overage: €1.19/TB ≈ $1.30. OVH: generally unmetered.",
    )

    st.sidebar.subheader("Fleet")
    num_servers = st.sidebar.number_input("Number of servers", value=3, min_value=1, step=1)

    # Derived values
    usable_storage_per_server_tb = server_storage_tb * (storage_usable_pct / 100)
    total_pool_storage_tb = usable_storage_per_server_tb * num_servers
    total_pool_bw_tb = server_bw_included_tb * num_servers

else:
    # ─────────────────────────────────────────────────
    # Sidebar: Component-based model inputs
    # ─────────────────────────────────────────────────
    st.sidebar.header("Component Costs")

    cpu_cost_core_mo = st.sidebar.number_input(
        "CPU cost ($/core/month)",
        value=4.50,
        step=0.50,
        help="Hetzner AX162-R: $215/mo ÷ 48 cores = $4.48/core/mo (but this includes RAM+storage+colo). "
        "Pure CPU amortisation on purchased hardware: 48-core EPYC server board+CPU ~$4000, "
        "5yr life ≈ $1.39/core/mo. The difference is your share of fixed costs.",
    )

    ram_cost_gb_mo = st.sidebar.number_input(
        "RAM cost ($/GB/month)",
        value=0.35,
        step=0.05,
        format="%.2f",
        help="Based on DDR5 ECC RDIMM pricing (March 2026):\n"
        "- DDR4 32GB RDIMM: $200-460 → $6-14/GB purchase → $0.10-0.24/GB/mo (5yr)\n"
        "- DDR5 32GB RDIMM: $540-1300 → $17-41/GB purchase → $0.28-0.68/GB/mo (5yr)\n"
        "- DDR5 64GB RDIMM: $1900-3200 → $30-50/GB purchase → $0.50-0.83/GB/mo (5yr)\n\n"
        "Default $0.35 assumes DDR5 at mid-range pricing amortised over 5 years.",
    )

    nvme_cost_tb_yr = st.sidebar.number_input(
        "NVMe cost ($/TB/year)",
        value=40.0,
        step=5.0,
        help="Amortised cost of NVMe per TB per year.\n\n"
        "Research-based (5yr, March 2026):\n"
        "- Kioxia CM7-R 7.68TB: $29/TB/yr (best value)\n"
        "- Micron 7450 Pro 7.68TB: $35/TB/yr\n"
        "- Micron 7500 Pro 7.68TB: $62/TB/yr\n"
        "- Samsung PM9A3 3.84TB: $78/TB/yr\n\n"
        "⚠️ NAND crisis: prices ~246% above Q1 2025.",
    )

    avg_storage_utilisation_pct = st.sidebar.slider(
        "Avg customer storage utilisation (%)", min_value=10, max_value=100, value=50, step=5,
        help="What percentage of their storage plan does the average customer actually use? "
        "This lets you overcommit storage. See server-share mode for more details.",
    )

    electricity_kwh = st.sidebar.number_input(
        "Electricity ($/kWh)", value=0.20, step=0.01, format="%.3f",
        help="EU industrial: €0.15-0.25/kWh. US average: $0.10-0.15/kWh.",
    )

    server_watts = st.sidebar.number_input(
        "Avg server power draw (watts)", value=250, step=10,
        help="EPYC 9454P TDP 290W + memory + NVMe + cooling (PUE 1.3-1.5). "
        "Idle: ~100-150W. Loaded: 300-400W. Average: ~200-300W.",
    )

    colo_cost_mo = st.sidebar.number_input(
        "Datacenter / colo ($/month per server)",
        value=50.0,
        step=10.0,
        help="If renting (Hetzner/OVH): $0 — it's included in rental.\n"
        "If colocating in EU: Hetzner 1/3 rack (14U) = €100/mo for ~4 servers = ~€25/server.\n"
        "US colo: $36-56/U/mo depending on market. Full rack $870-2675/mo.",
    )

    num_servers = st.sidebar.number_input("Number of servers", value=3, min_value=1, step=1)

    bandwidth_cost_tb = st.sidebar.number_input(
        "Bandwidth cost ($/TB)", value=1.30, step=0.10, format="%.2f",
        help="Hetzner overage: €1.19/TB. Most plans include 20TB+. OVH: unmetered.",
    )

# ─────────────────────────────────────────────────
# Sidebar: Operational costs (shared by both modes)
# ─────────────────────────────────────────────────
st.sidebar.header("Operational Costs")

support_fte_cost_yr = st.sidebar.number_input(
    "Support FTE cost ($/year)", value=60000, step=5000,
    help="Fully-loaded annual cost per support engineer.",
)

customers_per_support_fte = st.sidebar.number_input(
    "Customers per support FTE", value=500, min_value=10, step=50,
    help="How many customers one support engineer can handle.",
)

platform_eng_cost_mo = st.sidebar.number_input(
    "Platform engineering overhead ($/month)",
    value=15000,
    step=1000,
    help="Total monthly cost of platform/SRE team amortised across all customers.",
)

target_margin_pct = st.sidebar.slider(
    "Target gross margin (%)", min_value=10, max_value=80, value=50, step=5
)


# ─────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────
def support_cost_per_customer_mo():
    return (support_fte_cost_yr / 12) / customers_per_support_fte


def cost_per_customer_mo(cpu_cores: float, ram_gb: float, storage_gb: float, bandwidth_gb_mo: float):
    """Compute monthly cost-to-serve for one customer instance.

    Storage is scaled by avg_storage_utilisation_pct: customers don't fill their
    full quota on average, so the actual physical storage consumed (and thus
    the cost) is lower than the plan size.  This enables overcommitting storage.

    Server-share mode: baseline NVMe from server rental is a pooled resource.
    Each customer's compute share "pays for" a proportional slice.  Only storage
    beyond that included slice is charged at the NVMe expansion rate.
    """
    support = support_cost_per_customer_mo()
    # Actual storage consumed on average (plan * utilisation%)
    actual_storage_gb = storage_gb * (avg_storage_utilisation_pct / 100)

    if cost_mode == "Server-share (recommended)":
        # Compute: fraction of one server consumed by this customer
        cpu_frac = cpu_cores / server_cpu_cores
        ram_frac = ram_gb / server_ram_gb
        server_frac = max(cpu_frac, ram_frac)
        compute_cost = server_frac * server_cost_mo

        # Storage: baseline NVMe is included in the server rental.
        # The customer's compute share entitles them to a proportional slice
        # of one server's usable storage.  Anything beyond that is expansion.
        included_storage_gb = server_frac * usable_storage_per_server_tb * 1000
        extra_storage_gb = max(0, actual_storage_gb - included_storage_gb)
        storage_cost = (extra_storage_gb / 1000) * (nvme_cost_tb_yr / 12)

        # Bandwidth: included pool is proportional to compute share
        included_bw_tb = server_frac * server_bw_included_tb
        extra_bw_tb = max(0, (bandwidth_gb_mo / 1000) - included_bw_tb)
        bw_cost = extra_bw_tb * extra_bw_cost_tb

        return compute_cost + storage_cost + bw_cost + support
    else:
        cpu = cpu_cores * cpu_cost_core_mo
        ram = ram_gb * ram_cost_gb_mo
        storage = (actual_storage_gb / 1000) * (nvme_cost_tb_yr / 12)
        bw = (bandwidth_gb_mo / 1000) * bandwidth_cost_tb
        return cpu + ram + storage + bw + support


def cost_breakdown(cpu_cores: float, ram_gb: float, storage_gb: float, bandwidth_gb_mo: float):
    """Return a dict with cost components for display."""
    support = support_cost_per_customer_mo()
    actual_storage_gb = storage_gb * (avg_storage_utilisation_pct / 100)
    util_pct = avg_storage_utilisation_pct

    if cost_mode == "Server-share (recommended)":
        cpu_frac = cpu_cores / server_cpu_cores
        ram_frac = ram_gb / server_ram_gb
        server_frac = max(cpu_frac, ram_frac)
        bottleneck = "CPU" if cpu_frac >= ram_frac else "RAM"
        compute_cost = server_frac * server_cost_mo

        included_storage_gb = server_frac * usable_storage_per_server_tb * 1000
        extra_storage_gb = max(0, actual_storage_gb - included_storage_gb)
        storage_cost = (extra_storage_gb / 1000) * (nvme_cost_tb_yr / 12)

        included_bw_tb = server_frac * server_bw_included_tb
        extra_bw_tb = max(0, (bandwidth_gb_mo / 1000) - included_bw_tb)
        bw_cost = extra_bw_tb * extra_bw_cost_tb

        return {
            "Server share": f"{server_frac * 100:.2f}% ({bottleneck}-bound)",
            "Compute": f"${compute_cost:.2f}",
            "Avg usage": f"{actual_storage_gb:.0f}GB ({util_pct}% of {storage_gb:.0f}GB)",
            "Incl. storage": f"{included_storage_gb:.0f}GB",
            "Extra storage": f"${storage_cost:.2f}" + (f" ({extra_storage_gb:.0f}GB)" if extra_storage_gb > 0 else ""),
            "Bandwidth": f"${bw_cost:.2f}",
            "Support": f"${support:.2f}",
        }
    else:
        return {
            "CPU": f"${cpu_cores * cpu_cost_core_mo:.2f}",
            "RAM": f"${ram_gb * ram_cost_gb_mo:.2f}",
            "Storage": f"${(actual_storage_gb / 1000) * (nvme_cost_tb_yr / 12):.2f} ({actual_storage_gb:.0f}GB @ {util_pct}%)",
            "Bandwidth": f"${(bandwidth_gb_mo / 1000) * bandwidth_cost_tb:.2f}",
            "Support": f"${support:.2f}",
        }


def price_from_cost(cost: float):
    return cost / (1 - target_margin_pct / 100)


# ─────────────────────────────────────────────────
# Tab layout
# ─────────────────────────────────────────────────
tab_infra, tab_immich, tab_nextcloud, tab_vaultwarden, tab_scenario = st.tabs(
    ["Infrastructure Overview", "Immich (Photos)", "Nextcloud (Files)", "Vaultwarden (Passwords)", "Scenario Planner"]
)

# ═════════════════════════════════════════════════
# Tab: Infrastructure Overview
# ═════════════════════════════════════════════════
with tab_infra:
    st.header("Infrastructure Baseline")

    if cost_mode == "Server-share (recommended)":
        st.subheader("Reference Server")
        ref_col1, ref_col2, ref_col3, ref_col4 = st.columns(4)
        ref_col1.metric("Monthly cost", f"${server_cost_mo:.0f}")
        ref_col2.metric("CPU cores", f"{server_cpu_cores}")
        ref_col3.metric("RAM", f"{server_ram_gb} GB")
        ref_col4.metric("NVMe per server", f"{usable_storage_per_server_tb:.1f} TB usable")

        st.subheader("Derived unit costs (for reference only)")
        st.caption("These show what the server effectively costs per unit — useful for comparison, but the model uses server-share fractions for compute and separate NVMe pricing for storage.")
        d1, d2, d3 = st.columns(3)
        d1.metric("Effective $/core/mo", f"${server_cost_mo / server_cpu_cores:.2f}")
        d2.metric("Effective $/GB RAM/mo", f"${server_cost_mo / server_ram_gb:.2f}")
        d3.metric("NVMe $/TB/mo", f"${nvme_cost_tb_yr / 12:.2f}")

        st.subheader("Cluster fleet")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Servers", f"{num_servers}")
        f2.metric("Fleet compute cost", f"${server_cost_mo * num_servers:,.0f}/mo")
        f3.metric("Total cores", f"{server_cpu_cores * num_servers}")
        f4.metric("Pooled storage", f"{total_pool_storage_tb:.1f} TB (baseline)")

        st.caption("Storage is pooled across the cluster and can be expanded with additional NVMe independently of compute servers.")

    else:
        st.subheader("Component unit costs")
        ref = pd.DataFrame({
            "Resource": ["NVMe Storage", "CPU Core", "RAM", "Bandwidth"],
            "Unit Cost": [
                f"${nvme_cost_tb_yr / 12:.2f}/TB/mo (${nvme_cost_tb_yr:.0f}/TB/yr)",
                f"${cpu_cost_core_mo:.2f}/core/mo",
                f"${ram_cost_gb_mo:.2f}/GB/mo",
                f"${bandwidth_cost_tb:.2f}/TB",
            ],
        })
        st.dataframe(ref, hide_index=True, use_container_width=True)

        kwh_per_month = (server_watts / 1000) * 24 * 30.44
        elec_per_server = kwh_per_month * electricity_kwh
        col1, col2, col3 = st.columns(3)
        col1.metric("Electricity / server", f"${elec_per_server:.2f}/mo")
        col2.metric("Colo / server", f"${colo_cost_mo:.2f}/mo")
        col3.metric("Total infra (all servers)", f"${(elec_per_server + colo_cost_mo) * num_servers:,.2f}/mo")

    st.subheader("Operational costs")
    op1, op2, op3 = st.columns(3)
    op1.metric("Support / customer", f"${support_cost_per_customer_mo():.2f}/mo")
    op2.metric("Platform eng overhead", f"${platform_eng_cost_mo:,.0f}/mo")
    op3.metric("Target margin", f"{target_margin_pct}%")

    # Research reference section
    st.subheader("Pricing research reference (March 2026)")
    with st.expander("Server rental pricing"):
        st.markdown("""
| Provider | Model | CPU | Cores | RAM | NVMe | Price |
|---|---|---|---|---|---|---|
| Hetzner | AX42 | Ryzen 7 PRO 8700GE | 8c/16t | 64GB DDR5 | 2x 512GB | €49/mo |
| Hetzner | AX52 | Ryzen 7 7700 | 8c/16t | 64GB DDR5 | 2x 1TB | €64/mo |
| Hetzner | EX101 | i9-13900 | 24c/32t | 64GB DDR5 | 2x 1.92TB | €89/mo |
| Hetzner | AX102 | Ryzen 9 7950X3D | 16c/32t | 128GB DDR5 | 2x 1.92TB | €109/mo |
| Hetzner | EX130-R | Xeon Gold 5412U | 24c/48t | 256GB DDR5 ECC | 2x 1.92TB | €134/mo |
| Hetzner | AX162-R | EPYC 9454P | 48c/96t | 256GB DDR5 ECC | 2x 3.84TB | €199/mo |
| OVH | Advance-2 | EPYC 4344P | 8c/16t | 64GB DDR5 ECC | 2x 960GB | $160-173/mo |
| OVH | RISE-L | Ryzen 9 9950X | 16c/32t | 128GB | 960GB | $177/mo |

⚠️ Hetzner prices increasing ~10-37% after April 1, 2026.
        """)

    with st.expander("NVMe SSD pricing (enterprise, 5yr amortisation)"):
        st.markdown("""
| Drive | Capacity | Purchase $/TB | Amortised $/TB/yr |
|---|---|---|---|
| Kioxia CM7-R | 7.68TB | $147/TB | **$29/TB/yr** |
| Micron 7450 Pro | 7.68TB | $174/TB | **$35/TB/yr** |
| Micron 7450 Pro | 3.84TB | $190/TB | **$38/TB/yr** |
| Micron 7500 Pro | 7.68TB | $312/TB | **$62/TB/yr** |
| Samsung PM9A3 | 3.84TB | $390/TB | **$78/TB/yr** |

⚠️ NAND prices have risen ~246% since Q1 2025 (AI/HBM demand consuming fab capacity).
        """)

    with st.expander("Server RAM pricing"):
        st.markdown("""
| Type | Capacity | Purchase $/GB | Amortised $/GB/mo (5yr) |
|---|---|---|---|
| DDR4 ECC RDIMM | 32GB | $6-14/GB | $0.10-0.24 |
| DDR4 ECC RDIMM | 64GB | $6-9/GB | $0.10-0.16 |
| DDR5 ECC RDIMM | 32GB | $17-41/GB | $0.28-0.68 |
| DDR5 ECC RDIMM | 64GB | $30-50/GB | $0.50-0.83 |
| DDR5 ECC RDIMM | 128GB | $38/GB | $0.63 |

⚠️ DRAM prices rising 20%+ in H1 2026 due to AI demand. DDR4 supply tightening.
        """)

# ═════════════════════════════════════════════════
# Tab: Immich
# ═════════════════════════════════════════════════
with tab_immich:
    st.header("Immich — Photo Management")

    st.subheader("Competitor Reference: Ente.io")
    ente_df = pd.DataFrame({
        "Tier": ["50 GB", "200 GB", "1 TB", "2 TB"],
        "Ente Monthly": ["$2.99", "$5.99", "$11.99", "$23.99"],
        "Ente Annual (per mo)": ["$2.49", "$4.99", "$9.99", "$19.99"],
    })
    st.dataframe(ente_df, hide_index=True, use_container_width=True)

    st.subheader("Resource Assumptions per Customer")

    immich_col1, immich_col2 = st.columns(2)
    with immich_col1:
        immich_cpu = st.number_input("CPU cores (Immich)", value=0.25, step=0.05, key="immich_cpu",
                                     help="Avg CPU per instance. ML tasks (thumbnails, face detection) are bursty.")
        immich_ram = st.number_input("RAM GB (Immich)", value=2.0, step=0.25, key="immich_ram",
                                     help="Based on capacity analysis (91k-asset instance): ~1.6GiB after "
                                     "restart, rising to ~2.1GiB from V8 heap fragmentation. 2.0GiB is the "
                                     "recommended budget (server + ML worker + Redis + PostgreSQL).")
    with immich_col2:
        immich_bw = st.number_input("Bandwidth GB/mo (Immich)", value=20.0, step=5.0, key="immich_bw",
                                    help="Photo uploads + thumbnail views + sharing.")
        immich_db_overhead_pct = st.number_input("DB overhead % of storage tier", value=15.0, step=5.0, key="immich_db_oh",
                                                  help="PostgreSQL + Redis storage as % of photo storage.")

    st.subheader("Tier Pricing Analysis")

    immich_tiers_gb = [50, 200, 1000, 2000]
    ente_monthly = [2.99, 5.99, 11.99, 23.99]
    ente_annual = [2.49, 4.99, 9.99, 19.99]

    rows = []
    for i, tier_gb in enumerate(immich_tiers_gb):
        effective_storage = tier_gb * (1 + immich_db_overhead_pct / 100)
        cost = cost_per_customer_mo(immich_cpu, immich_ram, effective_storage, immich_bw)
        suggested = price_from_cost(cost)
        breakdown = cost_breakdown(immich_cpu, immich_ram, effective_storage, immich_bw)
        row = {"Tier": f"{tier_gb} GB", "Total Cost": f"${cost:.2f}", "Suggested Price": f"${suggested:.2f}",
               "Ente Price": f"${ente_monthly[i]:.2f}", "vs Ente": f"{((suggested / ente_monthly[i]) - 1) * 100:+.0f}%"}
        row.update(breakdown)
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.subheader("Margin if Matching Competitor Price")
    margin_rows = []
    for i, tier_gb in enumerate(immich_tiers_gb):
        effective_storage = tier_gb * (1 + immich_db_overhead_pct / 100)
        cost = cost_per_customer_mo(immich_cpu, immich_ram, effective_storage, immich_bw)
        for label, comp_price in [("Ente monthly", ente_monthly[i]), ("Ente annual", ente_annual[i])]:
            margin = ((comp_price - cost) / comp_price) * 100 if comp_price > 0 else 0
            margin_rows.append({
                "Tier": f"{tier_gb} GB", "Competitor": label,
                "Their Price": f"${comp_price:.2f}", "Our Cost": f"${cost:.2f}",
                "Margin": f"{margin:.1f}%",
                "Viable?": "✓" if margin >= 20 else "✗" if margin < 0 else "~",
            })
    st.dataframe(pd.DataFrame(margin_rows), hide_index=True, use_container_width=True)

# ═════════════════════════════════════════════════
# Tab: Nextcloud
# ═════════════════════════════════════════════════
with tab_nextcloud:
    st.header("Nextcloud — File Sync & Collaboration")

    st.subheader("Competitor Reference")
    comp_df = pd.DataFrame({
        "Service": [
            "Proton Drive Plus", "Proton Unlimited", "pCloud 500GB", "pCloud 2TB",
            "LibreCloud 1TB", "LibreCloud 2TB",
        ],
        "Storage": ["200 GB", "500 GB", "500 GB", "2 TB", "1 TB", "2 TB"],
        "Monthly": ["$4.99", "$12.99", "$4.99", "$9.99", "$9.99", "$19.99"],
        "Annual (per mo)": ["$3.99", "$9.99", "$4.17", "$8.33", "$7.99", "$12.99"],
        "Notes": [
            "Bundled w/ mail+VPN", "Bundled w/ full suite", "Storage only", "Storage only",
            "Hosted NC, 10 users", "Hosted NC, 25 users",
        ],
    })
    st.dataframe(comp_df, hide_index=True, use_container_width=True)

    st.subheader("Resource Assumptions per Customer")

    nc_col1, nc_col2 = st.columns(2)
    with nc_col1:
        nc_cpu = st.number_input("CPU cores (Nextcloud)", value=0.15, step=0.05, key="nc_cpu",
                                 help="Nextcloud is mostly I/O bound. PHP workers are lightweight.")
        nc_ram = st.number_input("RAM GB (Nextcloud)", value=0.75, step=0.25, key="nc_ram",
                                 help="PHP + PostgreSQL + occasional Collabora usage.")
    with nc_col2:
        nc_bw = st.number_input("Bandwidth GB/mo (Nextcloud)", value=30.0, step=5.0, key="nc_bw",
                                help="File sync is bidirectional — more bandwidth than photos.")
        nc_db_overhead_pct = st.number_input("DB overhead % of storage tier", value=5.0, step=2.0, key="nc_db_oh",
                                             help="PostgreSQL metadata is smaller for file sync.")

    st.subheader("Tier Pricing Analysis")

    nc_tiers_gb = [100, 500, 1000, 2000]

    nc_rows = []
    for tier_gb in nc_tiers_gb:
        effective_storage = tier_gb * (1 + nc_db_overhead_pct / 100)
        cost = cost_per_customer_mo(nc_cpu, nc_ram, effective_storage, nc_bw)
        suggested = price_from_cost(cost)
        breakdown = cost_breakdown(nc_cpu, nc_ram, effective_storage, nc_bw)
        row = {"Tier": f"{tier_gb} GB", "Total Cost": f"${cost:.2f}", "Suggested Price": f"${suggested:.2f}"}
        row.update(breakdown)
        nc_rows.append(row)
    st.dataframe(pd.DataFrame(nc_rows), hide_index=True, use_container_width=True)

    st.subheader("Margin at Competitor-Equivalent Prices")
    nc_comp_prices = {
        100: ("Proton Drive Plus 200GB", 4.99),
        500: ("pCloud 500GB", 4.99),
        1000: ("LibreCloud 1TB", 7.99),
        2000: ("pCloud 2TB", 8.33),
    }
    nc_margin_rows = []
    for tier_gb in nc_tiers_gb:
        effective_storage = tier_gb * (1 + nc_db_overhead_pct / 100)
        cost = cost_per_customer_mo(nc_cpu, nc_ram, effective_storage, nc_bw)
        comp_name, comp_price = nc_comp_prices[tier_gb]
        margin = ((comp_price - cost) / comp_price) * 100 if comp_price > 0 else 0
        nc_margin_rows.append({
            "Tier": f"{tier_gb} GB", "Nearest Competitor": comp_name,
            "Their Price": f"${comp_price:.2f}", "Our Cost": f"${cost:.2f}",
            "Margin": f"{margin:.1f}%",
            "Viable?": "✓" if margin >= 20 else "✗" if margin < 0 else "~",
        })
    st.dataframe(pd.DataFrame(nc_margin_rows), hide_index=True, use_container_width=True)

# ═════════════════════════════════════════════════
# Tab: Vaultwarden
# ═════════════════════════════════════════════════
with tab_vaultwarden:
    st.header("Vaultwarden — Password Manager")

    st.subheader("Competitor Reference: Bitwarden")
    bw_df = pd.DataFrame({
        "Plan": ["Free", "Premium", "Families (6 users)", "Teams", "Enterprise"],
        "Price": ["$0", "$1.65/mo", "$3.99/mo", "$4/user/mo", "$6/user/mo"],
        "Notes": [
            "Unlimited passwords, unlimited devices",
            "TOTP, 5GB attachments, vault health",
            "6 premium accounts, unlimited sharing",
            "Event logging, API, directory integration",
            "SSO, SCIM, custom policies",
        ],
    })
    st.dataframe(bw_df, hide_index=True, use_container_width=True)

    st.subheader("Resource Assumptions per Customer")
    st.info("Vaultwarden is extremely lightweight — SQLite backend, minimal CPU/RAM, negligible storage.")

    vw_col1, vw_col2 = st.columns(2)
    with vw_col1:
        vw_cpu = st.number_input("CPU cores (Vaultwarden)", value=0.02, step=0.01, format="%.3f", key="vw_cpu",
                                 help="Mostly idle, brief spikes on sync.")
        vw_ram = st.number_input("RAM GB (Vaultwarden)", value=0.064, step=0.016, format="%.3f", key="vw_ram",
                                 help="~64MB typical for Vaultwarden process.")
    with vw_col2:
        vw_storage = st.number_input("Storage GB (Vaultwarden)", value=0.5, step=0.1, key="vw_storage",
                                     help="SQLite DB + file attachments. Most users < 100MB.")
        vw_bw = st.number_input("Bandwidth GB/mo (Vaultwarden)", value=0.5, step=0.1, key="vw_bw",
                                help="Password sync is tiny — mostly small JSON payloads.")

    st.subheader("Pricing Analysis")

    vw_cost = cost_per_customer_mo(vw_cpu, vw_ram, vw_storage, vw_bw)
    vw_breakdown = cost_breakdown(vw_cpu, vw_ram, vw_storage, vw_bw)

    st.write("**Cost breakdown (individual):**")
    st.json(vw_breakdown)

    vw_plans = [
        {"Plan": "Individual", "Users": 1, "Multiplier": 1.0},
        {"Plan": "Family", "Users": 6, "Multiplier": 2.5},
    ]

    vw_rows = []
    for plan in vw_plans:
        plan_cost = vw_cost * plan["Multiplier"]
        plan_price = price_from_cost(plan_cost)
        vw_rows.append({
            "Plan": plan["Plan"], "Users": plan["Users"],
            "Our Cost": f"${plan_cost:.2f}", "Suggested Price": f"${plan_price:.2f}",
        })
    st.dataframe(pd.DataFrame(vw_rows), hide_index=True, use_container_width=True)

    st.subheader("Margin at Bitwarden Prices")
    bw_prices = [("Premium (individual)", 1.65, 1.0), ("Families (6 users)", 3.99, 2.5)]
    bw_margin_rows = []
    for label, comp_price, mult in bw_prices:
        plan_cost = vw_cost * mult
        margin = ((comp_price - plan_cost) / comp_price) * 100 if comp_price > 0 else 0
        bw_margin_rows.append({
            "Bitwarden Plan": label, "Their Price": f"${comp_price:.2f}",
            "Our Cost": f"${plan_cost:.2f}", "Margin": f"{margin:.1f}%",
            "Viable?": "✓" if margin >= 20 else "✗" if margin < 0 else "~",
        })
    st.dataframe(pd.DataFrame(bw_margin_rows), hide_index=True, use_container_width=True)

# ═════════════════════════════════════════════════
# Tab: Scenario Planner
# ═════════════════════════════════════════════════
with tab_scenario:
    st.header("Scenario Planner")
    st.write("Model revenue, costs, and margin for a given customer mix.")

    st.subheader("Customer Counts by Tier")

    scen_col1, scen_col2, scen_col3 = st.columns(3)

    with scen_col1:
        st.write("**Immich**")
        immich_counts = {}
        for tier_gb in immich_tiers_gb:
            immich_counts[tier_gb] = st.number_input(
                f"Immich {tier_gb}GB customers", value=0, min_value=0, step=10, key=f"scen_immich_{tier_gb}"
            )

    with scen_col2:
        st.write("**Nextcloud**")
        nc_counts = {}
        for tier_gb in nc_tiers_gb:
            nc_counts[tier_gb] = st.number_input(
                f"Nextcloud {tier_gb}GB customers", value=0, min_value=0, step=10, key=f"scen_nc_{tier_gb}"
            )

    with scen_col3:
        st.write("**Vaultwarden**")
        vw_individual = st.number_input("VW Individual customers", value=0, min_value=0, step=10, key="scen_vw_ind")
        vw_family = st.number_input("VW Family customers", value=0, min_value=0, step=10, key="scen_vw_fam")

    st.subheader("Price Overrides ($/mo per customer)")
    st.write("Set your actual prices. Defaults are the suggested prices at target margin.")

    price_col1, price_col2, price_col3 = st.columns(3)

    immich_prices = {}
    with price_col1:
        st.write("**Immich**")
        for tier_gb in immich_tiers_gb:
            effective_storage = tier_gb * (1 + immich_db_overhead_pct / 100)
            default_price = price_from_cost(cost_per_customer_mo(immich_cpu, immich_ram, effective_storage, immich_bw))
            immich_prices[tier_gb] = st.number_input(
                f"Immich {tier_gb}GB price", value=round(default_price, 2), step=0.50,
                key=f"price_immich_{tier_gb}", format="%.2f"
            )

    nc_prices = {}
    with price_col2:
        st.write("**Nextcloud**")
        for tier_gb in nc_tiers_gb:
            effective_storage = tier_gb * (1 + nc_db_overhead_pct / 100)
            default_price = price_from_cost(cost_per_customer_mo(nc_cpu, nc_ram, effective_storage, nc_bw))
            nc_prices[tier_gb] = st.number_input(
                f"NC {tier_gb}GB price", value=round(default_price, 2), step=0.50,
                key=f"price_nc_{tier_gb}", format="%.2f"
            )

    with price_col3:
        st.write("**Vaultwarden**")
        vw_ind_price = st.number_input(
            "VW Individual price", value=round(price_from_cost(vw_cost), 2), step=0.25,
            key="price_vw_ind", format="%.2f"
        )
        vw_fam_price = st.number_input(
            "VW Family price", value=round(price_from_cost(vw_cost * 2.5), 2), step=0.25,
            key="price_vw_fam", format="%.2f"
        )

    # Compute scenario
    st.subheader("Results")

    total_revenue = 0.0
    total_cost = 0.0
    total_customers = 0
    total_cpu_cores = 0.0
    total_ram_gb = 0.0
    total_storage_gb = 0.0
    detail_rows = []

    def _add(name, count, unit_cost, price, cpu, ram, storage):
        if count <= 0:
            return 0.0, 0.0, 0, 0.0, 0.0, 0.0
        rev = count * price
        cst = count * unit_cost
        # Physical storage = plan size * avg utilisation
        actual_storage = storage * (avg_storage_utilisation_pct / 100)
        detail_rows.append({
            "Product": name, "Customers": count,
            "Revenue/mo": f"${rev:,.2f}", "Cost/mo": f"${cst:,.2f}",
            "Margin": f"{((rev - cst) / rev) * 100:.1f}%" if rev > 0 else "N/A",
        })
        return rev, cst, count, count * cpu, count * ram, count * actual_storage

    _products = []

    for tier_gb in immich_tiers_gb:
        eff = tier_gb * (1 + immich_db_overhead_pct / 100)
        _products.append(_add(f"Immich {tier_gb}GB", immich_counts[tier_gb],
                              cost_per_customer_mo(immich_cpu, immich_ram, eff, immich_bw),
                              immich_prices[tier_gb], immich_cpu, immich_ram, eff))

    for tier_gb in nc_tiers_gb:
        eff = tier_gb * (1 + nc_db_overhead_pct / 100)
        _products.append(_add(f"Nextcloud {tier_gb}GB", nc_counts[tier_gb],
                              cost_per_customer_mo(nc_cpu, nc_ram, eff, nc_bw),
                              nc_prices[tier_gb], nc_cpu, nc_ram, eff))

    _products.append(_add("VW Individual", vw_individual, vw_cost, vw_ind_price, vw_cpu, vw_ram, vw_storage))
    _products.append(_add("VW Family", vw_family, vw_cost * 2.5, vw_fam_price, vw_cpu * 2.5, vw_ram * 2.5, vw_storage * 2.5))

    for _rev, _cst, _cnt, _cpu, _ram, _stor in _products:
        total_revenue += _rev
        total_cost += _cst
        total_customers += _cnt
        total_cpu_cores += _cpu
        total_ram_gb += _ram
        total_storage_gb += _stor

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Customers", f"{total_customers:,}")
    m2.metric("Monthly Revenue", f"${total_revenue:,.2f}")
    gross_margin = ((total_revenue - total_cost) / total_revenue * 100) if total_revenue > 0 else 0
    m3.metric("Gross Margin", f"{gross_margin:.1f}%")
    net_after_platform = total_revenue - total_cost - platform_eng_cost_mo
    m4.metric("Net after platform eng", f"${net_after_platform:,.2f}/mo")

    m5, m6, m7, m8 = st.columns(4)
    support_ftes = total_customers / customers_per_support_fte if total_customers > 0 else 0
    m5.metric("Support FTEs needed", f"{support_ftes:.1f}")
    arpu = total_revenue / total_customers if total_customers > 0 else 0
    m6.metric("ARPU", f"${arpu:.2f}/mo")
    m7.metric("Total cost/mo", f"${total_cost + platform_eng_cost_mo:,.2f}")
    annual_net = net_after_platform * 12
    m8.metric("Projected annual net", f"${annual_net:,.0f}")

    if cost_mode == "Server-share (recommended)" and total_customers > 0:
        st.subheader("Capacity & storage pool")
        cap1, cap2, cap3, cap4 = st.columns(4)
        fleet_cores = server_cpu_cores * num_servers
        fleet_ram = server_ram_gb * num_servers
        fleet_storage_gb = total_pool_storage_tb * 1000
        extra_storage_gb = max(0, total_storage_gb - fleet_storage_gb)
        extra_storage_cost = (extra_storage_gb / 1000) * (nvme_cost_tb_yr / 12)

        cap1.metric("CPU utilisation", f"{total_cpu_cores / fleet_cores * 100:.1f}%",
                     help=f"{total_cpu_cores:.1f} / {fleet_cores} cores")
        cap2.metric("RAM utilisation", f"{total_ram_gb / fleet_ram * 100:.1f}%",
                     help=f"{total_ram_gb:.1f} / {fleet_ram} GB")
        cap3.metric("Storage pool used", f"{total_storage_gb / 1000:.1f} / {total_pool_storage_tb:.1f} TB",
                     help=f"Baseline pool: {total_pool_storage_tb:.1f}TB from {num_servers} servers")
        if extra_storage_gb > 0:
            cap4.metric("Expansion NVMe needed", f"{extra_storage_gb / 1000:.1f} TB",
                         help=f"Extra cost: ${extra_storage_cost:,.2f}/mo at ${nvme_cost_tb_yr:.0f}/TB/yr")
        else:
            headroom_gb = fleet_storage_gb - total_storage_gb
            cap4.metric("Storage headroom", f"{headroom_gb / 1000:.1f} TB free")

    if detail_rows:
        st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)
    else:
        st.info("Enter customer counts above to see scenario results.")
