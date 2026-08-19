import os
import pandas as pd
from bokeh.io import output_file, save, show
from bokeh.layouts import column, row, Spacer
from bokeh.models import (
    ColumnDataSource, MultiSelect, Div, HoverTool, 
    LinearAxis, Range1d, CustomJS, FactorRange,
    NumeralTickFormatter
)
from bokeh.plotting import figure
from bokeh.transform import dodge
from bokeh.resources import INLINE

# -------------------------------------------------------------------------
# 1. DATA PREPARATION & PROCESSING
# -------------------------------------------------------------------------
def load_and_preprocess_data():
    """Loads insurance data from CSV and handles data cleaning & binning."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, '..', 'data', 'insurance_data_clean.csv')
    df = pd.read_csv(csv_path)

    # Ensure clean data types
    df['Year'] = df['Year'].astype(int)
    df['Active Producers'] = df['Active Producers'].fillna(0)
    df['Wrtn Prem'] = df['Wrtn Prem'].fillna(0)
    df['Loss Ratio'] = df['Loss Ratio'].fillna(0)
    df['Retention Ratio'] = df['Retention Ratio'].fillna(0)

    # Create Producer Bins
    bins = [-1, 9, 19, 29, 39, 49, 59, 69, 79, 89, 99, 109, 119, 9999]
    labels = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80-89', '90-99', '100-109', '110-119', '131+']
    df['Producer_Bin'] = pd.cut(df['Active Producers'], bins=bins, labels=labels).astype(str)

    raw_records = df[['Year', 'State', 'Prod Line', 'Prod Abbr', 'Wrtn Prem', 'Loss Ratio', 'Retention Ratio', 'Hit Ratio', 'Producer_Bin', 'Active Producers', 'Unified Growth Rate', 'Primary Agency Id']].to_dict(orient='records')

    years_list = [str(y) for y in sorted(df['Year'].unique())]
    states_list = ['MI', 'PA', 'WV', 'OH', 'KY', 'IN']

    return df, raw_records, years_list, states_list, labels, script_dir


# -------------------------------------------------------------------------
# 2. HELPER COMPONENTS & DATASOURCES
# -------------------------------------------------------------------------
def render_kpi_html(prem_b, loss_pct, ret_pct, agencies_cnt):
    """Generates initial HTML for KPI metric boxes."""
    return f"""
    <div style="display: flex; justify-content: space-between; width: 1040px; font-family: Segoe UI, sans-serif;">
        <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
            <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Total Written Premium</div>
            <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">${prem_b:.2f}B</div>
        </div>
        <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
            <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Average Loss Ratio</div>
            <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">{loss_pct:.1f}%</div>
        </div>
        <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
            <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Average Retention Rate</div>
            <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">{ret_pct:.1f}%</div>
        </div>
        <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
            <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Total Active Agencies</div>
            <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">{agencies_cnt:,}</div>
        </div>
    </div>
    """


def create_data_sources(df, years_list, states_list, labels):
    """Calculates initial aggregates and builds Bokeh ColumnDataSources."""
    # Chart 1
    c1_init = df.groupby(['Year', 'Prod Line'])['Wrtn Prem'].sum().unstack(fill_value=0)
    cds1 = ColumnDataSource(data=dict(
        years=years_list,
        CL=(c1_init['CL'] / 1e6).tolist() if 'CL' in c1_init else [0]*len(years_list),
        PL=(c1_init['PL'] / 1e6).tolist() if 'PL' in c1_init else [0]*len(years_list)
    ))

    # Chart 2
    c2_init = df.groupby('State').agg(Loss_Ratio=('Loss Ratio', 'mean'), Retention_Ratio=('Retention Ratio', 'mean')).reindex(states_list).fillna(0)
    cds2 = ColumnDataSource(data=dict(
        states=states_list,
        loss=c2_init['Loss_Ratio'].tolist(),
        ret=c2_init['Retention_Ratio'].tolist()
    ))

    # Chart 3
    c3_init = df.groupby(['Prod Abbr', 'Prod Line']).agg(Hit_Ratio=('Hit Ratio', 'mean'), Loss_Ratio=('Loss Ratio', 'mean'), Wrtn_Prem=('Wrtn Prem', 'sum')).reset_index()
    c3_init['Bubble_Size'] = 10 + (c3_init['Wrtn_Prem'] / (c3_init['Wrtn_Prem'].max() or 1)) * 35
    c3_init['Color'] = c3_init['Prod Line'].map({'CL': '#5B9BD5', 'PL': '#ED7D31'})
    cds3 = ColumnDataSource(data=dict(
        Prod_Abbr=c3_init['Prod Abbr'].tolist(),
        Prod_Line=c3_init['Prod Line'].tolist(),
        Hit_Ratio_Pct=(c3_init['Hit_Ratio'] * 100).tolist(),
        Loss_Ratio_Pct=(c3_init['Loss_Ratio'] * 100).tolist(),
        Bubble_Size=c3_init['Bubble_Size'].tolist(),
        Color=c3_init['Color'].tolist()
    ))

    # Chart 4
    c4_grp = df.groupby('Producer_Bin', observed=False).agg(
        Tot_Prem=('Wrtn Prem', 'sum'),
        Tot_Prod=('Active Producers', 'sum'),
        Growth=('Unified Growth Rate', 'mean')
    ).reindex(labels).fillna(0)

    c4_grp['Prem_Per_Producer'] = c4_grp.apply(lambda r: r['Tot_Prem'] / r['Tot_Prod'] if r['Tot_Prod'] > 0 else 0, axis=1)
    growth_vals_init = (c4_grp['Growth'] * 100).tolist()

    cds4 = ColumnDataSource(data=dict(
        bins=labels,
        prem=c4_grp['Prem_Per_Producer'].tolist(),
        growth=growth_vals_init
    ))

    return cds1, cds2, cds3, cds4, growth_vals_init


# -------------------------------------------------------------------------
# 3. BUILD UI COMPONENTS AND CHARTS
# -------------------------------------------------------------------------
def create_widgets_and_header(df, years_list, states_list):
    """Instantiates header, KPI Div, and multi-select filter controls."""
    init_tot_prem = df['Wrtn Prem'].sum() / 1e9
    init_loss_ratio = df['Loss Ratio'].mean() * 100
    init_ret_ratio = df['Retention Ratio'].mean() * 100
    init_agencies = df['Primary Agency Id'].nunique()

    header_div = Div(text="""
    <div style="background-color: #002060; color: white; padding: 14px 20px; border-radius: 4px; font-family: Segoe UI, sans-serif; width: 1280px; box-sizing: border-box; text-align: center;">
        <h2 style="margin: 0; font-size: 22px;">Insurance Portfolio Performance & Executive Dashboard</h2>
        <p style="margin: 4px 0 0 0; font-size: 13px; font-style: italic; color: #D9D9D9;">Data Period: 2005–2015 | 172,917 Portfolio Records</p>
    </div>
    """, width=1300)

    kpi_div = Div(text=render_kpi_html(init_tot_prem, init_loss_ratio, init_ret_ratio, init_agencies), width=1040)

    slicer_prod = MultiSelect(title="Prod Line", value=['CL', 'PL'], options=['CL', 'PL'], size=3, width=210)
    slicer_state = MultiSelect(title="State", value=states_list, options=states_list, size=6, width=210)
    slicer_year = MultiSelect(title="Year", value=years_list, options=years_list, size=11, width=210)

    return header_div, kpi_div, slicer_prod, slicer_state, slicer_year


def build_charts(cds1, cds2, cds3, cds4, years_list, states_list, labels, growth_vals_init):
    """Configures figure layouts, glyphs, and styling for all 4 charts."""
    p1 = figure(x_range=years_list, title="Annual Written Premium Trend (CL vs. PL)", height=320, width=500, tools="")
    p1.vbar_stack(['CL', 'PL'], x='years', width=0.6, color=['#5B9BD5', '#ED7D31'], source=cds1, legend_label=['CL', 'PL'])
    p1.yaxis.axis_label = "Total Premium (Millions)"
    p1.legend.location = "top_left"
    p1.legend.orientation = "horizontal"

    p2 = figure(y_range=states_list[::-1], title="State Performance: Loss Ratio vs. Retention", height=320, width=500, tools="", x_range=(0, 1.05))
    p2.hbar(y=dodge('states', 0.18, range=p2.y_range), right='loss', height=0.32, color='#C00000', source=cds2, legend_label="Loss Ratio")
    p2.hbar(y=dodge('states', -0.18, range=p2.y_range), right='ret', height=0.32, color='#70AD47', source=cds2, legend_label="Retention Ratio")
    p2.xaxis.formatter = NumeralTickFormatter(format="0%")
    p2.legend.location = "top_right"

    p3 = figure(title="Product Conversion vs. Underwriting Margin", height=320, width=500, tools="hover", x_range=(0, 32), y_range=(35, 75))
    p3.scatter(x='Hit_Ratio_Pct', y='Loss_Ratio_Pct', size='Bubble_Size', color='Color', alpha=0.6, source=cds3)
    p3.xaxis.axis_label = "Hit Ratio (%)"
    p3.yaxis.axis_label = "Loss Ratio (%)"
    hover3 = p3.select(type=HoverTool)
    hover3.tooltips = [("Product", "@Prod_Abbr"), ("Line", "@{Prod_Line}"), ("Hit Ratio", "@Hit_Ratio_Pct{0.0}%"), ("Loss Ratio", "@Loss_Ratio_Pct{0.0}%")]

    # Dynamic Growth Axis Range
    min_g = min(growth_vals_init) if growth_vals_init else 0
    max_g = max(growth_vals_init) if growth_vals_init else 10
    p4_growth_range = Range1d(start=min_g - 2, end=max_g + 2)

    p4 = figure(x_range=FactorRange(*labels), title="Producer Scaling vs. Growth Dynamics", height=320, width=500, tools="")
    p4.vbar(x='bins', top='prem', width=0.4, color='#5B9BD5', source=cds4, legend_label="Prem Per Producer")
    p4.yaxis.axis_label = "Prem Per Producer"
    p4.yaxis.formatter = NumeralTickFormatter(format="$0,0")

    p4.extra_y_ranges = {"growth_axis": p4_growth_range}
    p4.add_layout(LinearAxis(y_range_name="growth_axis", axis_label="Growth Rate (%)"), 'right')
    p4.line(x='bins', y='growth', y_range_name="growth_axis", color='#ED7D31', line_width=3, source=cds4, legend_label="Growth Rate")
    p4.xaxis.major_label_orientation = 0.8
    p4.legend.location = "top_right"

    for p in [p1, p2, p3, p4]:
        p.title.text_font_size = '12pt'
        p.title.text_font_style = 'bold'
        p.title.align = 'center'
        p.outline_line_color = '#D3D3D3'
        if p.legend:
            p.legend.border_line_color = None
            p.legend.background_fill_alpha = 0.6
            p.legend.label_text_font_size = "9pt"

    return p1, p2, p3, p4, p4_growth_range


# -------------------------------------------------------------------------
# 4. CALLBACK & LAYOUT SETUP
# -------------------------------------------------------------------------
def setup_js_callbacks(slicer_prod, slicer_state, slicer_year, cds1, cds2, cds3, cds4, kpi_div, p4_growth_range, raw_records, years_list, states_list, labels):
    """Defines and attaches CustomJS callback for reactive filter changes."""
    callback = CustomJS(args=dict(
        s_prod=slicer_prod, s_state=slicer_state, s_year=slicer_year,
        cds1=cds1, cds2=cds2, cds3=cds3, cds4=cds4,
        kpi_div=kpi_div, p4_growth_range=p4_growth_range,
        raw_records=raw_records,
        years_list=years_list, states_list=states_list, bin_labels=labels
    ), code="""
        function updateDashboard() {
            const prod_sel = s_prod.value || [];
            const state_sel = s_state.value || [];
            const year_sel = (s_year.value || []).map(String);

            // Filter Raw Data
            const filtered = raw_records.filter(r => 
                prod_sel.includes(String(r['Prod Line'])) &&
                state_sel.includes(String(r['State'])) &&
                year_sel.includes(String(r['Year']))
            );

            // Update KPIs
            let tot_prem = 0, loss_sum = 0, ret_sum = 0;
            const agencies = new Set();
            filtered.forEach(r => {
                tot_prem += (r['Wrtn Prem'] || 0);
                loss_sum += (r['Loss Ratio'] || 0);
                ret_sum += (r['Retention Ratio'] || 0);
                if (r['Primary Agency Id']) agencies.add(r['Primary Agency Id']);
            });

            const cnt = filtered.length;
            const prem_b = (tot_prem / 1e9).toFixed(2);
            const loss_pct = cnt > 0 ? ((loss_sum / cnt) * 100).toFixed(1) : '0.0';
            const ret_pct = cnt > 0 ? ((ret_sum / cnt) * 100).toFixed(1) : '0.0';
            const agencies_cnt = agencies.size.toLocaleString();

            kpi_div.text = `
            <div style="display: flex; justify-content: space-between; width: 1040px; font-family: Segoe UI, sans-serif;">
                <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
                    <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Total Written Premium</div>
                    <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">$${prem_b}B</div>
                </div>
                <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
                    <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Average Loss Ratio</div>
                    <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">${loss_pct}%</div>
                </div>
                <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
                    <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Average Retention Rate</div>
                    <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">${ret_pct}%</div>
                </div>
                <div style="background-color: #F4F5F7; width: 240px; padding: 12px; border-radius: 6px; text-align: center; border: 1px solid #E0E0E0;">
                    <div style="font-size: 11px; font-weight: bold; color: #555; text-transform: uppercase;">Total Active Agencies</div>
                    <div style="font-size: 24px; font-weight: bold; color: #002060; margin-top: 4px;">${agencies_cnt}</div>
                </div>
            </div>
            `;

            // 1. Re-aggregate Chart 1
            const c1_cl = {}, c1_pl = {};
            years_list.forEach(y => { c1_cl[y] = 0; c1_pl[y] = 0; });
            filtered.forEach(r => {
                const yStr = String(r['Year']);
                if (r['Prod Line'] === 'CL') c1_cl[yStr] = (c1_cl[yStr] || 0) + ((r['Wrtn Prem'] || 0) / 1e6);
                if (r['Prod Line'] === 'PL') c1_pl[yStr] = (c1_pl[yStr] || 0) + ((r['Wrtn Prem'] || 0) / 1e6);
            });

            cds1.data = {
                years: years_list,
                CL: years_list.map(y => c1_cl[y] || 0),
                PL: years_list.map(y => c1_pl[y] || 0)
            };
            cds1.change.emit();

            // 2. Re-aggregate Chart 2
            const c2_loss = {}, c2_ret = {}, c2_cnt = {};
            states_list.forEach(s => { c2_loss[s] = 0; c2_ret[s] = 0; c2_cnt[s] = 0; });
            filtered.forEach(r => {
                const s = String(r['State']);
                if (c2_loss.hasOwnProperty(s)) {
                    c2_loss[s] += (r['Loss Ratio'] || 0);
                    c2_ret[s] += (r['Retention Ratio'] || 0);
                    c2_cnt[s] += 1;
                }
            });

            cds2.data = {
                states: states_list,
                loss: states_list.map(s => c2_cnt[s] > 0 ? c2_loss[s] / c2_cnt[s] : 0),
                ret: states_list.map(s => c2_cnt[s] > 0 ? c2_ret[s] / c2_cnt[s] : 0)
            };
            cds2.change.emit();

            // 3. Re-aggregate Chart 3
            const c3_map = {};
            filtered.forEach(r => {
                const key = r['Prod Abbr'] + '|' + r['Prod Line'];
                if (!c3_map[key]) {
                    c3_map[key] = { hit: 0, loss: 0, prem: 0, cnt: 0, line: r['Prod Line'], abbr: r['Prod Abbr'] };
                }
                c3_map[key].hit += (r['Hit Ratio'] || 0);
                c3_map[key].loss += (r['Loss Ratio'] || 0);
                c3_map[key].prem += (r['Wrtn Prem'] || 0);
                c3_map[key].cnt += 1;
            });

            const abbrs = [], lines = [], hits = [], losses = [], sizes = [], colors = [];
            let max_prem = 1;
            Object.values(c3_map).forEach(v => { if (v.prem > max_prem) max_prem = v.prem; });

            Object.values(c3_map).forEach(v => {
                abbrs.push(v.abbr);
                lines.push(v.line);
                hits.push((v.hit / v.cnt) * 100);
                losses.push((v.loss / v.cnt) * 100);
                sizes.push(10 + (v.prem / max_prem) * 35);
                colors.push(v.line === 'CL' ? '#5B9BD5' : '#ED7D31');
            });

            cds3.data = {
                Prod_Abbr: abbrs,
                Prod_Line: lines,
                Hit_Ratio_Pct: hits,
                Loss_Ratio_Pct: losses,
                Bubble_Size: sizes,
                Color: colors
            };
            cds3.change.emit();

            // 4. Re-aggregate Chart 4 & Dynamically Adjust Growth Axis Bounds
            const c4_prem = {}, c4_prod = {}, c4_growth = {}, c4_cnt = {};
            bin_labels.forEach(b => { c4_prem[b] = 0; c4_prod[b] = 0; c4_growth[b] = 0; c4_cnt[b] = 0; });
            filtered.forEach(r => {
                const b = String(r['Producer_Bin']);
                if (b && c4_prem.hasOwnProperty(b)) {
                    c4_prem[b] += (r['Wrtn Prem'] || 0);
                    c4_prod[b] += (r['Active Producers'] || 0);
                    c4_growth[b] += (r['Unified Growth Rate'] || 0);
                    c4_cnt[b] += 1;
                }
            });

            const growth_vals = bin_labels.map(b => c4_cnt[b] > 0 ? (c4_growth[b] / c4_cnt[b]) * 100 : 0);
            
            // Dynamically adjust secondary growth axis thresholds
            if (growth_vals.length > 0) {
                let min_val = Math.min(...growth_vals);
                let max_val = Math.max(...growth_vals);
                let pad = (max_val - min_val) * 0.15 || 2;
                p4_growth_range.start = Math.floor(min_val - pad);
                p4_growth_range.end = Math.ceil(max_val + pad);
            }

            cds4.data = {
                bins: bin_labels,
                prem: bin_labels.map(b => c4_prod[b] > 0 ? c4_prem[b] / c4_prod[b] : 0),
                growth: growth_vals
            };
            cds4.change.emit();
        }

        // Attach listener
        updateDashboard();
    """)

    slicer_prod.js_on_change('value', callback)
    slicer_state.js_on_change('value', callback)
    slicer_year.js_on_change('value', callback)


def build_dashboard_layout(header_div, kpi_div, slicer_prod, slicer_state, slicer_year, p1, p2, p3, p4):
    """Assembles all components into the main grid layout."""
    slicers_layout = column(slicer_prod, Spacer(height=10), slicer_state, Spacer(height=10), slicer_year)

    col_left = column(p1, Spacer(height=15), p3)
    col_right = column(p2, Spacer(height=15), p4)
    charts_layout = row(col_left, Spacer(width=30), col_right)

    return column(
        header_div, 
        Spacer(height=15), 
        row(slicers_layout, Spacer(width=20), column(kpi_div, Spacer(height=15), charts_layout))
    )


# -------------------------------------------------------------------------
# 5. MAIN EXECUTION PIPELINE
# -------------------------------------------------------------------------
def main():
    """Main execution function."""
    # Data pipeline
    df, raw_records, years_list, states_list, labels, script_dir = load_and_preprocess_data()
    cds1, cds2, cds3, cds4, growth_vals_init = create_data_sources(df, years_list, states_list, labels)

    # UI and Visualization creation
    header_div, kpi_div, slicer_prod, slicer_state, slicer_year = create_widgets_and_header(df, years_list, states_list)
    p1, p2, p3, p4, p4_growth_range = build_charts(cds1, cds2, cds3, cds4, years_list, states_list, labels, growth_vals_init)

    # Interactivity & Layout assembly
    setup_js_callbacks(
        slicer_prod, slicer_state, slicer_year, 
        cds1, cds2, cds3, cds4, 
        kpi_div, p4_growth_range, 
        raw_records, years_list, states_list, labels
    )

    main_layout = build_dashboard_layout(header_div, kpi_div, slicer_prod, slicer_state, slicer_year, p1, p2, p3, p4)

    # Output generation
    out_html = os.path.join(script_dir, "index.html")
    output_file(out_html, title="Executive Insurance Dashboard")
    save(main_layout, resources=INLINE)

    print(f"Dashboard created successfully at: {out_html}")
    show(main_layout)


if __name__ == "__main__":
    main()