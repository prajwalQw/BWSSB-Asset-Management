"""
Build and format slides 6 to 12 of Government First Pitch Deck.
Strictly follows:
- 10 x 7.5 in (4:3) template format
- Arial 11 pt, 1.5 line spacing for all body and table text
- Short bold labels mirroring template questions
- Clean margins (>0.4 in), no text overflow, no overlapping elements
- Honesty rules and Government submission guidelines
"""

import os
import sys
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls

TRL_STATEMENT = (
    "TRL 4 to 5 today: working system prototype validated in the lab on public BWSSB data "
    "and labelled simulation. Pilot goal: reach TRL 7 by running it on live BWSSB data at "
    "one pumping station and one supply zone (DMA)."
)

def add_highlight(run):
    """Adds yellow highlight to a text run."""
    ns = nsdecls("a")
    xml_str = f'<a:highlight {ns}><a:srgbClr val="FFFF00"/></a:highlight>'
    run._r.get_or_add_rPr().append(parse_xml(xml_str))

def style_title(slide, title_text):
    """Formats title placeholder to single-line Arial 22pt bold."""
    t = slide.shapes.title
    t.left = Inches(0.6)
    t.top = Inches(0.32)
    t.width = Inches(8.8)
    t.height = Inches(0.48)
    tf = t.text_frame
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    p.font.name = "Arial"
    p.font.size = Pt(22)
    p.font.bold = True
    p.font.color.rgb = RGBColor(15, 44, 89)
    r = p.add_run()
    r.text = title_text
    r.font.name = "Arial"
    r.font.size = Pt(22)
    r.font.bold = True
    r.font.color.rgb = RGBColor(15, 44, 89)

def style_paragraph(p, bold_prefix="", text="", line_spacing=1.5, space_after=1, is_highlighted=False, font_size=11):
    p.font.name = "Arial"
    p.font.size = Pt(font_size)
    p.line_spacing = line_spacing
    p.space_after = Pt(space_after)
    
    if bold_prefix:
        r0 = p.add_run()
        r0.text = bold_prefix + (" " if not bold_prefix.endswith(" ") else "")
        r0.font.bold = True
        r0.font.name = "Arial"
        r0.font.size = Pt(font_size)
        r0.font.color.rgb = RGBColor(15, 23, 42)
    
    if text:
        r1 = p.add_run()
        r1.text = text
        r1.font.bold = False
        r1.font.name = "Arial"
        r1.font.size = Pt(font_size)
        r1.font.color.rgb = RGBColor(30, 41, 59)
        if is_highlighted or "[FILL:" in text:
            add_highlight(r1)

def style_table_cell(cell, text="", bold_prefix="", is_header=False, is_highlight=False, font_size=11, align=PP_ALIGN.LEFT):
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cell.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.08)
    tf.margin_right = Inches(0.08)
    tf.margin_top = Inches(0.02)
    tf.margin_bottom = Inches(0.02)
    tf.clear()
    p = tf.paragraphs[0]
    p.alignment = align
    p.font.name = "Arial"
    p.font.size = Pt(font_size)
    p.line_spacing = 1.5
    
    if is_header:
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(230, 238, 248)
        r = p.add_run()
        r.text = text
        r.font.bold = True
        r.font.name = "Arial"
        r.font.size = Pt(font_size)
        r.font.color.rgb = RGBColor(15, 23, 42)
    else:
        if bold_prefix:
            r0 = p.add_run()
            r0.text = bold_prefix + (" " if not bold_prefix.endswith(" ") else "")
            r0.font.bold = True
            r0.font.name = "Arial"
            r0.font.size = Pt(font_size)
            r0.font.color.rgb = RGBColor(15, 23, 42)
        if text:
            r1 = p.add_run()
            r1.text = text
            r1.font.name = "Arial"
            r1.font.size = Pt(font_size)
            r1.font.color.rgb = RGBColor(30, 41, 59)
            if is_highlight or "[FILL:" in text:
                add_highlight(r1)

def clear_content_shapes(slide):
    """Keeps title and slide number placeholder, removes old content placeholders."""
    to_remove = []
    for s in slide.shapes:
        if s == slide.shapes.title:
            continue
        if "Slide Number" in s.name or "Footer" in s.name:
            continue
        to_remove.append(s)
    for s in to_remove:
        sp = s._element
        sp.getparent().remove(sp)

def build_presentation(input_pptx="Pitch_deck.pptx", output_pptx="Pitch_deck_filled.pptx"):
    prs = pptx.Presentation(input_pptx)
    print(f"Loaded presentation: {len(prs.slides)} slides.")

    # ==========================================
    # SLIDE 6: 1. Product/ Solution - Innovation
    # ==========================================
    s6 = prs.slides[5]
    clear_content_shapes(s6)
    style_title(s6, "1. Product/ Solution - Innovation")
    
    txBox6 = s6.shapes.add_textbox(Inches(0.6), Inches(0.82), Inches(8.8), Inches(2.20))
    tf6 = txBox6.text_frame
    tf6.word_wrap = True
    tf6.margin_left = tf6.margin_right = tf6.margin_top = tf6.margin_bottom = 0
    
    bullets_s6 = [
        ("Innovation:", "Intelligent asset management bringing GIS, SCADA and IoT into one view."),
        ("1st of its kind?:", "No, an improvement. Adds cross-asset analytics over pump AI."),
        ("Unique:", "Flow-balance leak range, pump health via voltage/current, P0-P3 ranking, advice."),
        ("Target customer:", "BWSSB and urban water supply and sewerage boards across Karnataka."),
        ("Need:", "Find failures early, reduce water loss, prevent pump trips, know what to fix."),
        ("How we deliver:", "Live asset map, early alert popups, ranked work orders, one-click reports."),
        ("Better than others:", "Unified view, open standards, explainable rules, engineer approval."),
        ("Key note:", "Built on public data; ready for real data. Can also deliver a full digital twin.")
    ]
    for idx, (pfx, txt) in enumerate(bullets_s6):
        p = tf6.paragraphs[0] if idx == 0 else tf6.add_paragraph()
        style_paragraph(p, bold_prefix=pfx, text=txt, line_spacing=1.5, space_after=1)

    img_path6 = os.path.join("deck_assets", "2_solution_overview.png")
    if os.path.exists(img_path6):
        left = Inches(2.88)
        top = Inches(3.20)
        width = Inches(4.24)
        height = Inches(2.65)
        pic6 = s6.shapes.add_picture(img_path6, left, top, width, height)
        pic6.line.color.rgb = RGBColor(203, 213, 225)
        pic6.line.width = Pt(1)
        
        cap_box6 = s6.shapes.add_textbox(Inches(0.6), Inches(5.92), Inches(8.8), Inches(0.28))
        cp6 = cap_box6.text_frame.paragraphs[0]
        cp6.alignment = PP_ALIGN.CENTER
        style_paragraph(cp6, bold_prefix="Figure:", text="Intelligent Asset Management, solution overview.", line_spacing=1.5, space_after=0)

    # ==========================================
    # SLIDE 7: 2. Product/ Solution - Readiness Level
    # ==========================================
    s7 = prs.slides[6]
    clear_content_shapes(s7)
    style_title(s7, "2. Product/ Solution - Readiness Level")
    
    txBox7 = s7.shapes.add_textbox(Inches(0.6), Inches(0.85), Inches(8.8), Inches(1.10))
    tf7 = txBox7.text_frame
    tf7.word_wrap = True
    tf7.margin_left = tf7.margin_right = tf7.margin_top = tf7.margin_bottom = 0
    
    p1 = tf7.paragraphs[0]
    style_paragraph(p1, bold_prefix="Current stage:", text="Concept  |  ", line_spacing=1.5, space_after=1)
    r_mvp = p1.add_run()
    r_mvp.text = "Prototype/MVP (working software prototype)"
    r_mvp.font.bold = True
    r_mvp.font.name = "Arial"
    r_mvp.font.size = Pt(11)
    r_mvp.font.color.rgb = RGBColor(15, 23, 42)
    r_tail = p1.add_run()
    r_tail.text = "  |  Live / Early Traction  |  Growth Stage"
    r_tail.font.name = "Arial"
    r_tail.font.size = Pt(11)
    r_tail.font.color.rgb = RGBColor(100, 116, 139)
    
    p2 = tf7.add_paragraph()
    style_paragraph(p2, bold_prefix="Technology Readiness Level:", text=TRL_STATEMENT, line_spacing=1.5, space_after=1)
    
    p3 = tf7.add_paragraph()
    style_paragraph(p3, bold_prefix="Data used:", text="Public internet data plus labelled simulation; ready for real BWSSB data.", line_spacing=1.5, space_after=1)

    frame_y7 = Inches(2.15)
    frame_h7 = Inches(0.65)
    frame_w7 = Inches(2.78)
    gap7 = Inches(0.23)
    
    frames_data = [
        ("Asset map of Bengaluru", Inches(0.6)),
        ("Pump voltage and current graphs", Inches(0.6) + frame_w7 + gap7),
        ("Leak alert popup", Inches(0.6) + (frame_w7 + gap7) * 2)
    ]
    for cap, x_pos in frames_data:
        box = s7.shapes.add_shape(MSO_SHAPE.RECTANGLE, x_pos, frame_y7, frame_w7, frame_h7)
        box.fill.background()
        box.line.color.rgb = RGBColor(148, 163, 184)
        box.line.width = Pt(1)
        box.line.dash_style = pptx.enum.dml.MSO_LINE.DASH
        tf_frame = box.text_frame
        tf_frame.word_wrap = True
        tf_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        p_frame = tf_frame.paragraphs[0]
        p_frame.alignment = PP_ALIGN.CENTER
        style_paragraph(p_frame, text=f"[Add screenshot: {cap}]", line_spacing=1.5, space_after=0)

    table_y7 = Inches(2.95)
    col_widths7 = [Inches(1.5), Inches(3.6), Inches(2.4), Inches(1.3)]
    
    table_data7 = [
        ("Feature", "What it does", "Technology", "Status"),
        ("Asset map (GIS)", "Pipes, pumps, tanks, lakes; zoom from city to station", "MapLibre, deck.gl, OpenStreetMap, BWSSB open GIS data", "Built"),
        ("Pump health", "Voltage, current, ON/OFF, start-up and drift alerts", "Median/MAD baselines, rule engine", "Built / Simulated"),
        ("Leak detection", "Flow in minus flow out minus use; loss estimate and location range", "Mass balance, EPANET/WNTR", "Built / Simulated"),
        ("Monitoring agent", "Joins alarms into one incident, suggests isolation and repair steps", "Python asyncio agent", "Built / Simulated"),
        ("Risk ranking", "Assets ranked P0 to P3 with reasons", "Weighted risk score model", "Built / Planned")
    ]
    
    table_shape7 = s7.shapes.add_table(len(table_data7), 4, Inches(0.6), table_y7, Inches(8.8), Inches(2.10))
    tbl7 = table_shape7.table
    for c_idx, w in enumerate(col_widths7):
        tbl7.columns[c_idx].width = w
        
    for r_idx, row in enumerate(table_data7):
        is_hdr = (r_idx == 0)
        for c_idx, val in enumerate(row):
            cell = tbl7.cell(r_idx, c_idx)
            style_table_cell(cell, text=val, is_header=is_hdr, font_size=11)

    # ==========================================
    # SLIDE 8: 3. Applicability to Government Use
    # ==========================================
    s8 = prs.slides[7]
    clear_content_shapes(s8)
    style_title(s8, "3. Applicability to Government Use")
    
    txBox8 = s8.shapes.add_textbox(Inches(0.6), Inches(0.82), Inches(8.8), Inches(1.70))
    tf8 = txBox8.text_frame
    tf8.word_wrap = True
    tf8.margin_left = tf8.margin_right = tf8.margin_top = tf8.margin_bottom = 0
    
    bullets_s8 = [
        ("Addresses the problem:", "One view of asset condition, early warnings and a ranked repair list for utility teams."),
        ("Fits government workflow:", "Views by role; alerts become advice; engineer approves every action; never auto-switches."),
        ("Effort to adopt:", "Software only at first; reads existing GIS and SCADA exports; zero change to field PLCs."),
        ("Works with existing systems:", "Designed for OPC-UA, Modbus and MQTT; adapters tested against simulators; read-only default."),
        ("Validation so far:", "Tested on public BWSSB data and simulated leak, pump and sensor scenarios. No pilot yet."),
        ("Pilot plan:", "Validate on live data at 1 station and 1 supply zone; measure slide 11 KPIs.")
    ]
    for idx, (pfx, txt) in enumerate(bullets_s8):
        p = tf8.paragraphs[0] if idx == 0 else tf8.add_paragraph()
        style_paragraph(p, bold_prefix=pfx, text=txt, line_spacing=1.5, space_after=1)

    img_path8 = os.path.join("deck_assets", "3_value_to_bwssb.png")
    if os.path.exists(img_path8):
        left = Inches(2.88)
        top = Inches(2.70)
        width = Inches(4.24)
        height = Inches(2.65)
        pic8 = s8.shapes.add_picture(img_path8, left, top, width, height)
        pic8.line.color.rgb = RGBColor(203, 213, 225)
        pic8.line.width = Pt(1)
        
        cap_box8 = s8.shapes.add_textbox(Inches(0.6), Inches(5.42), Inches(8.8), Inches(0.28))
        cp8 = cap_box8.text_frame.paragraphs[0]
        cp8.alignment = PP_ALIGN.CENTER
        style_paragraph(cp8, bold_prefix="Figure:", text="Value to BWSSB, outcomes and measurable impact.", line_spacing=1.5, space_after=0)

    # ==========================================
    # SLIDE 9: 4. Scalability of the Solution
    # ==========================================
    s9 = prs.slides[8]
    clear_content_shapes(s9)
    style_title(s9, "4. Scalability of the Solution")
    
    txBox9 = s9.shapes.add_textbox(Inches(0.6), Inches(0.85), Inches(8.8), Inches(1.35))
    tf9 = txBox9.text_frame
    tf9.word_wrap = True
    tf9.margin_left = tf9.margin_right = tf9.margin_top = tf9.margin_bottom = 0
    
    bullets_s9 = [
        ("Multi-Department Applicability:", "The same platform can be adapted for other urban water boards and city bodies (water supply, sewage, borewells) with changes to settings, not code. It can also be extended to a full digital twin for water management."),
        ("Geographical Scalability:", "Networks, pumps, tariffs and limits are in config files, nothing is hard-coded to Bengaluru. A new city needs its GIS layers and asset list loaded. Works for large cities and smaller towns."),
        ("Technical scale:", "Runs in containers; data layer can move from SQLite to PostgreSQL/PostGIS (planned).")
    ]
    for idx, (pfx, txt) in enumerate(bullets_s9):
        p = tf9.paragraphs[0] if idx == 0 else tf9.add_paragraph()
        style_paragraph(p, bold_prefix=pfx, text=txt, line_spacing=1.5, space_after=2)

    lbl9 = s9.shapes.add_textbox(Inches(0.6), Inches(2.35), Inches(8.8), Inches(0.28))
    lp9 = lbl9.text_frame.paragraphs[0]
    style_paragraph(lp9, bold_prefix="Proposed plan:", text="Phased scale-up roadmap from pilot to state-wide adoption", line_spacing=1.5, space_after=0)

    box_w9 = Inches(2.08)
    box_gap9 = Inches(0.16)
    box_y9 = Inches(2.70)
    box_h9 = Inches(2.95)
    
    phases = [
        ("Phase 1", "Months 1-3", "1 pumping station + 1 supply zone\n\n• Validate live data\n• Test leak alerts\n• Calibrate baseline\n• Train operators"),
        ("Phase 2", "Months 4-6", "One full division\n\n• Multiple stations\n• Multiple wards\n• Energy tariff optimization\n• Incident reports"),
        ("Phase 3", "Months 7-12", "Bengaluru core network\n\n• Cauvery trunk corridors\n• Major city GLRs\n• Full risk ranking (P0-P3)\n• Cross-zone balance"),
        ("Phase 4", "Year 2", "Other Karnataka boards\n\n• Multi-city deployment\n• Tier-2 urban water boards\n• Central dashboard\n• Enterprise SLA")
    ]
    for idx, (ph_title, ph_time, ph_desc) in enumerate(phases):
        x = Inches(0.6) + idx * (box_w9 + box_gap9)
        box = s9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, box_y9, box_w9, box_h9)
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(248, 250, 252) if idx > 0 else RGBColor(238, 242, 255)
        box.line.color.rgb = RGBColor(59, 130, 246) if idx == 0 else RGBColor(203, 213, 225)
        box.line.width = Pt(1.5 if idx == 0 else 1)
        
        tf_ph = box.text_frame
        tf_ph.word_wrap = True
        tf_ph.margin_left = tf_ph.margin_right = tf_ph.margin_top = tf_ph.margin_bottom = Inches(0.1)
        
        p_t = tf_ph.paragraphs[0]
        style_paragraph(p_t, bold_prefix=ph_title, text=f" ({ph_time})", line_spacing=1.5, space_after=4)
        p_d = tf_ph.add_paragraph()
        style_paragraph(p_d, text=ph_desc, line_spacing=1.5, space_after=0, font_size=11)

    # ==========================================
    # SLIDE 10: 5. Integration Capability of the Solution
    # ==========================================
    s10 = prs.slides[9]
    clear_content_shapes(s10)
    style_title(s10, "5. Integration Capability of the Solution")
    
    txBox10 = s10.shapes.add_textbox(Inches(0.6), Inches(0.85), Inches(8.8), Inches(1.40))
    tf10 = txBox10.text_frame
    tf10.word_wrap = True
    tf10.margin_left = tf10.margin_right = tf10.margin_top = tf10.margin_bottom = 0
    
    bullets_s10 = [
        ("Integration Readiness:", "Built for BWSSB GIS, SCADA and IoT adapters; lab-tested on public and simulated feeds; telemetry bridge ready."),
        ("System Compatibility:", "OPC-UA, Modbus TCP, MQTT, REST, GeoJSON; adapters simulator-tested; live field feeds planned for pilot."),
        ("Interoperability & Security:", "Unified data model; role logins (RBAC), rate limits and audit log; read-only field access.")
    ]
    for idx, (pfx, txt) in enumerate(bullets_s10):
        p = tf10.paragraphs[0] if idx == 0 else tf10.add_paragraph()
        style_paragraph(p, bold_prefix=pfx, text=txt, line_spacing=1.5, space_after=2)

    dia_y10 = Inches(2.55)
    dia_h10 = Inches(3.00)
    
    stages = [
        ("BWSSB Systems", "• GIS pipeline maps\n• SCADA pump telemetry\n• IoT edge meters\n• Maintenance records\n\nToday: public data + sim\nPilot: live BWSSB feeds", Inches(2.05), Inches(0.6)),
        ("Gateway Adapters", "• OPC-UA bridge\n• Modbus TCP\n• MQTT Sparkplug\n• REST / GeoJSON\n\nRead-only default", Inches(1.75), Inches(2.85)),
        ("Asset Platform", "• Unified data model\n• Mass balance engine\n• Pump health (MAD)\n• Risk priority (P0-P3)\n• Monitoring agent", Inches(2.05), Inches(4.80)),
        ("Decision Support", "• Early failure alerts\n• Ranked repair list\n• Engineer advice\n• One-click reports\n• Secure REST APIs", Inches(1.85), Inches(7.05))
    ]
    for s_idx, (st_title, st_desc, st_w, st_x) in enumerate(stages):
        box = s10.shapes.add_shape(MSO_SHAPE.RECTANGLE, st_x, dia_y10, st_w, dia_h10)
        box.fill.solid()
        if s_idx == 0:
            box.fill.fore_color.rgb = RGBColor(241, 245, 249)
        elif s_idx == 1:
            box.fill.fore_color.rgb = RGBColor(238, 242, 255)
        elif s_idx == 2:
            box.fill.fore_color.rgb = RGBColor(236, 253, 245)
        else:
            box.fill.fore_color.rgb = RGBColor(254, 243, 199)
            
        box.line.color.rgb = RGBColor(148, 163, 184)
        box.line.width = Pt(1)
        
        tf_st = box.text_frame
        tf_st.word_wrap = True
        tf_st.margin_left = tf_st.margin_right = tf_st.margin_top = tf_st.margin_bottom = Inches(0.08)
        
        p_st0 = tf_st.paragraphs[0]
        style_paragraph(p_st0, bold_prefix=st_title, line_spacing=1.4, space_after=3)
        p_st1 = tf_st.add_paragraph()
        style_paragraph(p_st1, text=st_desc, line_spacing=1.5, space_after=0, font_size=11)
        
        if s_idx < 3:
            arrow_x = st_x + st_w + Inches(0.02)
            arrow_w = Inches(0.14)
            arrow = s10.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arrow_x, dia_y10 + Inches(1.2), arrow_w, Inches(0.25))
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = RGBColor(100, 116, 139)
            arrow.line.fill.background()

    # ==========================================
    # SLIDE 11: 6. Socio-Economic Impact of the Project
    # ==========================================
    s11 = prs.slides[10]
    clear_content_shapes(s11)
    style_title(s11, "6. Socio-Economic Impact of the Project")
    
    txBox11 = s11.shapes.add_textbox(Inches(0.6), Inches(0.85), Inches(8.8), Inches(1.30))
    tf11 = txBox11.text_frame
    tf11.word_wrap = True
    tf11.margin_left = tf11.margin_right = tf11.margin_top = tf11.margin_bottom = 0
    
    bullets_s11 = [
        ("Society:", "Fewer supply cuts from pump trips and faster leak repair give steadier water."),
        ("Environment & SDGs:", "Supports UN SDG 6 and 11 by cutting water loss and wasted energy."),
        ("Economy:", "Less lost water, less unplanned repair work, and lower pumping power bills."),
        ("Jobs in Karnataka:", "[FILL: number and type of jobs the company will create in Karnataka]"),
        ("Simple arithmetic:", "1 MLD saved = 1,000 m3/day = 365,000 m3/year. Rupee value set with BWSSB.")
    ]
    for idx, (pfx, txt) in enumerate(bullets_s11):
        p = tf11.paragraphs[0] if idx == 0 else tf11.add_paragraph()
        style_paragraph(p, bold_prefix=pfx, text=txt, line_spacing=1.5, space_after=1)

    table_y11 = Inches(2.45)
    col_w11 = [Inches(2.2), Inches(1.7), Inches(1.7), Inches(3.2)]
    
    tbl_data11 = [
        ("Measure", "Baseline", "Target", "How measured"),
        ("Time to detect a leak", "From BWSSB data", "To be agreed with BWSSB", "Mass-balance and pressure drop alert timestamp"),
        ("Litres lost per day", "From BWSSB data", "To be agreed with BWSSB", "Flow imbalance calculation before and after repair"),
        ("Unplanned pump downtime", "From BWSSB data", "To be agreed with BWSSB", "SCADA motor trip and maintenance log comparison"),
        ("Energy per m3 pumped", "From BWSSB data", "To be agreed with BWSSB", "Multifunction energy meter kWh divided by bulk flow m3")
    ]
    
    tbl_shape11 = s11.shapes.add_table(len(tbl_data11), 4, Inches(0.6), table_y11, Inches(8.8), Inches(2.10))
    tbl11 = tbl_shape11.table
    for c_idx, w in enumerate(col_w11):
        tbl11.columns[c_idx].width = w
        
    for r_idx, row in enumerate(tbl_data11):
        is_hdr = (r_idx == 0)
        for c_idx, val in enumerate(row):
            cell = tbl11.cell(r_idx, c_idx)
            style_table_cell(cell, text=val, is_header=is_hdr, font_size=11)

    # ==========================================
    # SLIDE 12: 7. Team Size, Background, Strength /Capability and Resources
    # ==========================================
    s12 = prs.slides[11]
    clear_content_shapes(s12)
    style_title(s12, "7. Team Size, Background, Strength /Capability and Resources")
    
    photo_w12 = Inches(1.85)
    photo_h12 = Inches(0.48)
    photo_gap12 = Inches(0.46)
    photo_y12 = Inches(0.82)
    
    for idx in range(4):
        px = Inches(0.6) + idx * (photo_w12 + photo_gap12)
        p_box = s12.shapes.add_shape(MSO_SHAPE.RECTANGLE, px, photo_y12, photo_w12, photo_h12)
        p_box.fill.background()
        p_box.line.color.rgb = RGBColor(148, 163, 184)
        p_box.line.width = Pt(1)
        p_box.line.dash_style = pptx.enum.dml.MSO_LINE.DASH
        tf_pb = p_box.text_frame
        tf_pb.vertical_anchor = MSO_ANCHOR.MIDDLE
        p_pb = tf_pb.paragraphs[0]
        p_pb.alignment = PP_ALIGN.CENTER
        style_paragraph(p_pb, text="[Add photo]", line_spacing=1.5, space_after=0, font_size=11)

    table_y12 = Inches(1.40)
    col_w12 = [Inches(1.2), Inches(1.4), Inches(1.3), Inches(1.3), Inches(1.7), Inches(1.9)]
    
    tbl_data12 = [
        ("Name", "Designation", "Exp / Qualification", "Previous Co worked", "Role in this project", "Founder / Member / Employee"),
        ("[FILL: Name 1]", "[FILL: Lead Architect]", "[FILL: B.E., X yrs]", "[FILL: Prev Co 1]", "[FILL: System Architecture]", "[FILL: Co-Founder]"),
        ("[FILL: Name 2]", "[FILL: IoT Lead]", "[FILL: B.E., X yrs]", "[FILL: Prev Co 2]", "[FILL: SCADA/IoT Gateway]", "[FILL: Founding Member]"),
        ("[FILL: Name 3]", "[FILL: AI / ML Lead]", "[FILL: B.Tech, X yrs]", "[FILL: Prev Co 3]", "[FILL: ML & Analytics Models]", "[FILL: Employee]"),
        ("[FILL: Name 4]", "[FILL: Full-Stack Lead]", "[FILL: B.E., X yrs]", "[FILL: Prev Co 4]", "[FILL: GIS & UI Platform]", "[FILL: Employee]")
    ]
    
    tbl_shape12 = s12.shapes.add_table(len(tbl_data12), 6, Inches(0.6), table_y12, Inches(8.8), Inches(1.80))
    tbl12 = tbl_shape12.table
    for c_idx, w in enumerate(col_w12):
        tbl12.columns[c_idx].width = w
        
    for r_idx, row in enumerate(tbl_data12):
        is_hdr = (r_idx == 0)
        for c_idx, val in enumerate(row):
            cell = tbl12.cell(r_idx, c_idx)
            style_table_cell(cell, text=val, is_header=is_hdr, font_size=11)

    txBox12 = s12.shapes.add_textbox(Inches(0.6), Inches(4.85), Inches(8.8), Inches(1.30))
    tf12 = txBox12.text_frame
    tf12.word_wrap = True
    tf12.margin_left = tf12.margin_right = tf12.margin_top = tf12.margin_bottom = 0
    
    p12_1 = tf12.paragraphs[0]
    style_paragraph(p12_1, bold_prefix="Our strength:", text="Robotics, automation, motor control, IoT and software engineering at Ignomagine Pvt. Ltd.; we built the prototype end to end. [FILL: add any water or utility experience]", line_spacing=1.5, space_after=3)
    
    p12_2 = tf12.add_paragraph()
    style_paragraph(p12_2, bold_prefix="Gap and plan:", text="[FILL: name the water/hydraulic domain advisor or partner, or write \"we will onboard a water-utility domain advisor and work with BWSSB engineers during the pilot\"].", line_spacing=1.5, space_after=0)

    prs.save(output_pptx)
    print(f"Successfully saved {output_pptx}.")

if __name__ == "__main__":
    build_presentation()
