"""
Subsidy Application Automation

This module automatically generates structured reports (JSON/XML) for 
significant anomalies and submits them to utility providers for 
investigation and potential subsidy applications.
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom

logger = logging.getLogger(__name__)


def generate_and_submit_report(
    db: Session,
    anomaly_id: str,
    report_type: str = "leak_investigation",
    utility_provider_email: str = None
) -> Dict[str, Any]:
    """
    Generate and submit subsidy report for a significant anomaly.
    
    Args:
        db: Database session
        anomaly_id: UUID of the detected anomaly
        report_type: Type of report (leak_investigation, spike_analysis, etc.)
        utility_provider_email: Email of the utility provider
    
    Returns:
        Report submission result with status and report data
    """
    # Import models
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.models import Anomaly, Meter, Property, SubsidyReport, MeterReading
    
    # Get anomaly details
    anomaly = db.query(Anomaly).filter(
        Anomaly.anomaly_id == anomaly_id
    ).first()
    
    if not anomaly:
        raise ValueError(f"Anomaly {anomaly_id} not found")
    
    # Get related meter and property
    meter = db.query(Meter).filter(Meter.meter_id == anomaly.meter_id).first()
    if not meter:
        raise ValueError(f"Meter {anomaly.meter_id} not found")
    
    property_obj = db.query(Property).filter(
        Property.property_id == meter.property_id
    ).first()
    
    # Get consumption data around the anomaly
    time_window = timedelta(hours=48)  # 48 hours window
    readings = db.query(MeterReading).filter(
        MeterReading.meter_id == anomaly.meter_id,
        MeterReading.timestamp >= anomaly.detected_at - time_window,
        MeterReading.timestamp <= anomaly.detected_at + time_window
    ).order_by(MeterReading.timestamp).all()
    
    # Build report data structure
    report_data = build_report_data(
        anomaly=anomaly,
        meter=meter,
        property_obj=property_obj,
        readings=readings,
        report_type=report_type
    )
    
    # Create subsidy report record
    subsidy_report = SubsidyReport(
        anomaly_id=anomaly_id,
        property_id=property_obj.property_id,
        meter_id=meter.meter_id,
        report_type=report_type,
        status='draft',
        utility_provider_email=utility_provider_email,
        report_data=report_data
    )
    
    db.add(subsidy_report)
    db.commit()
    db.refresh(subsidy_report)
    
    # Generate formatted reports
    json_report = generate_json_report(report_data)
    xml_report = generate_xml_report(report_data)
    
    # Submit to utility provider
    submission_result = submit_to_utility_provider(
        report_id=str(subsidy_report.report_id),
        json_report=json_report,
        xml_report=xml_report,
        utility_provider_email=utility_provider_email
    )
    
    # Update report status
    subsidy_report.status = submission_result['status']
    subsidy_report.submission_date = datetime.now()
    subsidy_report.response_data = submission_result
    db.commit()
    
    logger.info(f"Subsidy report {subsidy_report.report_id} submitted with status: {submission_result['status']}")
    
    return {
        "report_id": str(subsidy_report.report_id),
        "status": submission_result['status'],
        "submission_date": subsidy_report.submission_date.isoformat(),
        "report_data": report_data
    }


def build_report_data(
    anomaly: Any,
    meter: Any,
    property_obj: Any,
    readings: list,
    report_type: str
) -> Dict[str, Any]:
    """Build comprehensive report data structure"""
    
    # Calculate statistics from readings
    values = [float(r.value) for r in readings]
    avg_consumption = sum(values) / len(values) if values else 0
    max_consumption = max(values) if values else 0
    min_consumption = min(values) if values else 0
    
    # Determine if this qualifies for subsidy (e.g., continuous high consumption)
    is_qualifying = False
    qualification_reason = ""
    
    if anomaly.anomaly_type == "continuous_high":
        is_qualifying = True
        qualification_reason = "Continuous high consumption detected over extended period"
    elif anomaly.deviation_percentage > 100:
        is_qualifying = True
        qualification_reason = f"Significant consumption spike ({anomaly.deviation_percentage:.1f}% above normal)"
    elif anomaly.anomaly_type == "leak":
        is_qualifying = True
        qualification_reason = "Potential water/gas leak detected"
    
    report_data = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "report_version": "1.0",
            "report_type": report_type,
            "schema_version": "utility-subsidy-v1"
        },
        "property_information": {
            "property_id": str(property_obj.property_id),
            "property_name": property_obj.name,
            "address": {
                "street": property_obj.address,
                "city": property_obj.city,
                "postal_code": property_obj.postal_code,
                "country": property_obj.country
            },
            "property_type": property_obj.property_type,
            "total_area_sqm": float(property_obj.total_area) if property_obj.total_area else None,
            "number_of_units": property_obj.number_of_units
        },
        "meter_information": {
            "meter_id": str(meter.meter_id),
            "serial_number": meter.meter_serial_number,
            "meter_name": meter.meter_name,
            "utility_type_id": meter.utility_type_id,
            "installation_date": meter.installation_date.isoformat() if meter.installation_date else None,
            "communication_protocol": meter.communication_protocol,
            "location_description": meter.location_description
        },
        "anomaly_details": {
            "anomaly_id": str(anomaly.anomaly_id),
            "detected_at": anomaly.detected_at.isoformat(),
            "anomaly_type": anomaly.anomaly_type,
            "severity": anomaly.severity,
            "deviation_percentage": float(anomaly.deviation_percentage),
            "expected_value": float(anomaly.expected_value) if anomaly.expected_value else None,
            "actual_value": float(anomaly.actual_value),
            "description": anomaly.description
        },
        "consumption_analysis": {
            "analysis_period_hours": 48,
            "data_points_analyzed": len(readings),
            "average_consumption": round(avg_consumption, 2),
            "maximum_consumption": round(max_consumption, 2),
            "minimum_consumption": round(min_consumption, 2),
            "readings": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "value": float(r.value),
                    "unit": r.unit,
                    "is_anomaly": r.is_anomaly_detected
                }
                for r in readings
            ]
        },
        "subsidy_qualification": {
            "is_qualifying": is_qualifying,
            "qualification_reason": qualification_reason,
            "estimated_excess_consumption": round(max(0, anomaly.actual_value - (anomaly.expected_value or 0)), 2),
            "recommended_action": "Investigation and potential refund/credit" if is_qualifying else "Monitoring recommended"
        },
        "contact_information": {
            "company_name": property_obj.user.company_name if hasattr(property_obj, 'user') and property_obj.user else "N/A",
            "report_generated_by": "Utility Monitoring SaaS Platform",
            "support_contact": "support@utility-monitoring.example.com"
        }
    }
    
    return report_data


def generate_json_report(report_data: Dict[str, Any]) -> str:
    """Generate formatted JSON report"""
    return json.dumps(report_data, indent=2, ensure_ascii=False)


def generate_xml_report(report_data: Dict[str, Any]) -> str:
    """Generate formatted XML report"""
    
    def dict_to_xml(parent, data):
        """Recursively convert dictionary to XML elements"""
        for key, value in data.items():
            # Sanitize key for XML element name
            xml_key = key.replace(' ', '_').replace('-', '_')
            
            if isinstance(value, dict):
                child = ET.SubElement(parent, xml_key)
                dict_to_xml(child, value)
            elif isinstance(value, list):
                child = ET.SubElement(parent, xml_key)
                for item in value:
                    if isinstance(item, dict):
                        item_elem = ET.SubElement(child, "item")
                        dict_to_xml(item_elem, item)
                    else:
                        item_elem = ET.SubElement(child, "item")
                        item_elem.text = str(item)
            else:
                child = ET.SubElement(parent, xml_key)
                child.text = str(value) if value is not None else ""
    
    # Create root element
    root = ET.Element("UtilitySubsidyReport")
    root.set("version", "1.0")
    root.set("generated", datetime.now().isoformat())
    
    # Convert report data to XML
    dict_to_xml(root, report_data)
    
    # Pretty print XML
    xml_str = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ")
    
    # Remove extra blank lines
    lines = pretty_xml.split('\n')
    clean_lines = [line for line in lines if line.strip()]
    
    return '\n'.join(clean_lines)


def submit_to_utility_provider(
    report_id: str,
    json_report: str,
    xml_report: str,
    utility_provider_email: str = None
) -> Dict[str, Any]:
    """
    Submit report to utility provider.
    
    In production, this would:
    1. Send email with attachments
    2. Call utility provider's API endpoint
    3. Upload to a portal via web scraping/API
    4. Log submission for audit trail
    
    For now, simulates the submission process.
    """
    
    # Simulate API submission
    submission_result = {
        "status": "submitted",
        "submission_method": "api",
        "submission_timestamp": datetime.now().isoformat(),
        "tracking_id": f"SUB-{report_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "provider_reference": None,
        "response_code": 200,
        "message": "Report successfully submitted to utility provider"
    }
    
    # If email is provided, simulate email sending
    if utility_provider_email:
        try:
            # In production, use smtplib or email service like SendGrid
            # import smtplib
            # from email.mime.multipart import MIMEMultipart
            # from email.mime.application import MIMEApplication
            
            logger.info(f"Would send email to {utility_provider_email} with report {report_id}")
            
            submission_result["email_sent"] = True
            submission_result["email_recipient"] = utility_provider_email
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            submission_result["email_sent"] = False
            submission_result["email_error"] = str(e)
    
    # Simulate API call to utility provider
    # In production:
    # import requests
    # response = requests.post(
    #     "https://api.utility-provider.com/subsidy-claims",
    #     json=json.loads(json_report),
    #     headers={"Authorization": "Bearer API_KEY"}
    # )
    # submission_result["provider_reference"] = response.json().get("claim_id")
    
    logger.info(f"Simulated submission of report {report_id} to utility provider")
    
    return submission_result


def check_qualifying_anomalies(db: Session, property_id: str = None) -> Dict[str, Any]:
    """
    Scan for anomalies that qualify for subsidy applications.
    
    Criteria for qualification:
    - Continuous high consumption over weekend/non-business hours
    - Deviation > 100% from expected consumption
    - Anomaly type indicates potential leak
    - Severity is 'high' or 'critical'
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.models import Anomaly, SubsidyReport
    
    # Build query
    query = db.query(Anomaly).filter(
        Anomaly.is_resolved == False,
        Anomaly.severity.in_(["high", "critical"])
    )
    
    if property_id:
        from models.models import Meter
        meters = db.query(Meter).filter(Meter.property_id == property_id).all()
        meter_ids = [str(m.meter_id) for m in meters]
        query = query.filter(Anomaly.meter_id.in_(meter_ids))
    
    # Check for weekend anomalies (Saturday=5, Sunday=6)
    qualifying_anomalies = []
    
    for anomaly in query.all():
        is_qualifying = False
        reason = []
        
        # Check deviation
        if anomaly.deviation_percentage > 100:
            is_qualifying = True
            reason.append(f"High deviation: {anomaly.deviation_percentage:.1f}%")
        
        # Check anomaly type
        if anomaly.anomaly_type in ["continuous_high", "leak"]:
            is_qualifying = True
            reason.append(f"Type: {anomaly.anomaly_type}")
        
        # Check if occurred on weekend
        day_of_week = anomaly.detected_at.weekday()
        if day_of_week >= 5:  # Weekend
            is_qualifying = True
            reason.append("Occurred on weekend")
        
        # Check if already has a report
        existing_report = db.query(SubsidyReport).filter(
            SubsidyReport.anomaly_id == anomaly.anomaly_id
        ).first()
        
        if existing_report:
            continue  # Skip if already reported
        
        if is_qualifying:
            qualifying_anomalies.append({
                "anomaly_id": str(anomaly.anomaly_id),
                "meter_id": str(anomaly.meter_id),
                "detected_at": anomaly.detected_at.isoformat(),
                "anomaly_type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "deviation_percentage": float(anomaly.deviation_percentage),
                "qualification_reasons": reason,
                "recommended_action": "Generate subsidy report"
            })
    
    return {
        "scan_timestamp": datetime.now().isoformat(),
        "qualifying_anomalies_count": len(qualifying_anomalies),
        "qualifying_anomalies": qualifying_anomalies
    }


def auto_generate_reports_for_qualifying_anomalies(
    db: Session,
    utility_provider_email: str,
    property_id: str = None
) -> Dict[str, Any]:
    """
    Automatically generate and submit reports for all qualifying anomalies.
    
    This can be run as a scheduled task (e.g., daily).
    """
    qualifying = check_qualifying_anomalies(db, property_id)
    
    results = {
        "execution_timestamp": datetime.now().isoformat(),
        "total_qualifying": qualifying["qualifying_anomalies_count"],
        "reports_generated": 0,
        "reports_failed": 0,
        "report_ids": []
    }
    
    for anomaly_info in qualifying["qualifying_anomalies"]:
        try:
            report_result = generate_and_submit_report(
                db=db,
                anomaly_id=anomaly_info["anomaly_id"],
                report_type="automatic_detection",
                utility_provider_email=utility_provider_email
            )
            
            results["reports_generated"] += 1
            results["report_ids"].append(report_result["report_id"])
            
        except Exception as e:
            logger.error(f"Failed to generate report for anomaly {anomaly_info['anomaly_id']}: {str(e)}")
            results["reports_failed"] += 1
    
    return results
