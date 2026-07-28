"""
Subsidy Application Automation.

This module handles automatic generation and submission of subsidy reports
when significant anomalies are detected (e.g., continuous high consumption).
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import logging
from uuid import UUID
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.models import Anomaly, Meter, Property, MeterReading, SubsidyReport, UtilityType

logger = logging.getLogger(__name__)


def fetch_anomaly_details(db: Session, anomaly_id: UUID) -> Dict[str, Any]:
    """
    Fetch complete details for an anomaly including meter and property info.
    
    Args:
        db: Database session
        anomaly_id: UUID of the anomaly
    
    Returns:
        Dictionary with complete anomaly details
    """
    anomaly = db.query(Anomaly).filter(Anomaly.anomaly_id == anomaly_id).first()
    
    if not anomaly:
        raise ValueError(f"Anomaly {anomaly_id} not found")
    
    meter = db.query(Meter).filter(Meter.meter_id == anomaly.meter_id).first()
    property_obj = db.query(Property).filter(Property.property_id == meter.property_id).first()
    utility_type = db.query(UtilityType).filter(
        UtilityType.utility_type_id == meter.utility_type_id
    ).first()
    
    return {
        'anomaly': anomaly,
        'meter': meter,
        'property': property_obj,
        'utility_type': utility_type
    }


def fetch_historical_consumption(db: Session, meter_id: UUID, 
                                days: int = 30) -> list:
    """
    Fetch historical consumption data for the report.
    
    Args:
        db: Database session
        meter_id: UUID of the meter
        days: Number of days of history
    
    Returns:
        List of consumption records
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    readings = db.query(
        MeterReading.reading_timestamp,
        MeterReading.consumption_value,
        MeterReading.unit_of_measurement
    ).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.reading_timestamp >= start_date
    ).order_by(MeterReading.reading_timestamp).all()
    
    return [
        {
            'timestamp': r.reading_timestamp.isoformat(),
            'value': float(r.consumption_value),
            'unit': r.unit_of_measurement
        }
        for r in readings
    ]


def generate_json_report(anomaly_data: Dict[str, Any], 
                        historical_data: list,
                        include_history: bool = True) -> Dict[str, Any]:
    """
    Generate a JSON-formatted subsidy report.
    
    Args:
        anomaly_data: Complete anomaly details
        historical_data: Historical consumption data
        include_history: Whether to include historical data
    
    Returns:
        JSON-serializable dictionary
    """
    anomaly = anomaly_data['anomaly']
    meter = anomaly_data['meter']
    property_obj = anomaly_data['property']
    utility_type = anomaly_data['utility_type']
    
    report = {
        "report_metadata": {
            "report_id": str(UUID(int=1)),  # Will be replaced with actual UUID
            "generated_at": datetime.utcnow().isoformat(),
            "report_type": "subsidy_application",
            "version": "1.0"
        },
        "property_information": {
            "property_id": str(property_obj.property_id),
            "property_name": property_obj.property_name,
            "property_type": property_obj.property_type,
            "address": {
                "line1": property_obj.address_line1,
                "line2": property_obj.address_line2 or "",
                "city": property_obj.city,
                "state_province": property_obj.state_province or "",
                "postal_code": property_obj.postal_code,
                "country": property_obj.country
            },
            "coordinates": {
                "latitude": float(meter.latitude) if meter.latitude else None,
                "longitude": float(meter.longitude) if meter.longitude else None
            }
        },
        "meter_information": {
            "meter_id": str(meter.meter_id),
            "meter_serial_number": meter.meter_serial_number,
            "meter_name": meter.meter_name or "",
            "utility_type": utility_type.utility_name,
            "unit_of_measurement": utility_type.unit_of_measurement,
            "installation_date": meter.installation_date.isoformat() if meter.installation_date else None,
            "communication_protocol": meter.communication_protocol or ""
        },
        "anomaly_details": {
            "anomaly_id": str(anomaly.anomaly_id),
            "detection_timestamp": anomaly.detection_timestamp.isoformat(),
            "anomaly_type": anomaly.anomaly_type,
            "severity_level": anomaly.severity_level,
            "deviation_percentage": float(anomaly.deviation_percentage) if anomaly.deviation_percentage else None,
            "expected_value": float(anomaly.expected_value) if anomaly.expected_value else None,
            "actual_value": float(anomaly.actual_value) if anomaly.actual_value else None,
            "description": anomaly.description
        },
        "consumption_analysis": {
            "estimated_excess_consumption": float(anomaly.actual_value - anomaly.expected_value) if anomaly.actual_value and anomaly.expected_value else None,
            "estimated_excess_cost": float((anomaly.actual_value - anomaly.expected_value) * utility_type.cost_per_unit) if anomaly.actual_value and anomaly.expected_value else None,
            "carbon_footprint_impact": float((anomaly.actual_value - anomaly.expected_value) * utility_type.carbon_factor) if anomaly.actual_value and anomaly.expected_value else None
        }
    }
    
    if include_history:
        report["historical_consumption"] = {
            "period_days": 30,
            "data_points": len(historical_data),
            "readings": historical_data
        }
    
    # Subsidy request section
    report["subsidy_request"] = {
        "request_type": "investigation_and_subsidy",
        "reason": f"Unusual {anomaly.anomaly_type} detected indicating potential equipment malfunction or external factor beyond consumer control",
        "requested_action": [
            "Investigate cause of anomalous consumption",
            "Verify meter accuracy",
            "Consider adjustment or subsidy for excess charges"
        ],
        "supporting_documentation": "Automated detection via smart meter monitoring system"
    }
    
    return report


def generate_xml_report(anomaly_data: Dict[str, Any],
                       historical_data: list,
                       include_history: bool = True) -> str:
    """
    Generate an XML-formatted subsidy report.
    
    Args:
        anomaly_data: Complete anomaly details
        historical_data: Historical consumption data
        include_history: Whether to include historical data
    
    Returns:
        Formatted XML string
    """
    # Create root element
    root = ET.Element("SubsidyApplicationReport")
    root.set("version", "1.0")
    root.set("generatedAt", datetime.utcnow().isoformat())
    
    # Property information
    property_obj = anomaly_data['property']
    meter = anomaly_data['meter']
    
    property_elem = ET.SubElement(root, "PropertyInformation")
    ET.SubElement(property_elem, "PropertyId").text = str(property_obj.property_id)
    ET.SubElement(property_elem, "PropertyName").text = property_obj.property_name
    ET.SubElement(property_elem, "PropertyType").text = property_obj.property_type
    
    address_elem = ET.SubElement(property_elem, "Address")
    ET.SubElement(address_elem, "Line1").text = property_obj.address_line1
    ET.SubElement(address_elem, "Line2").text = property_obj.address_line2 or ""
    ET.SubElement(address_elem, "City").text = property_obj.city
    ET.SubElement(address_elem, "PostalCode").text = property_obj.postal_code
    ET.SubElement(address_elem, "Country").text = property_obj.country
    
    # Meter information
    meter_elem = ET.SubElement(root, "MeterInformation")
    ET.SubElement(meter_elem, "MeterId").text = str(meter.meter_id)
    ET.SubElement(meter_elem, "SerialNumber").text = meter.meter_serial_number
    ET.SubElement(meter_elem, "UtilityType").text = anomaly_data['utility_type'].utility_name
    
    # Anomaly details
    anomaly = anomaly_data['anomaly']
    anomaly_elem = ET.SubElement(root, "AnomalyDetails")
    ET.SubElement(anomaly_elem, "AnomalyId").text = str(anomaly.anomaly_id)
    ET.SubElement(anomaly_elem, "DetectionTimestamp").text = anomaly.detection_timestamp.isoformat()
    ET.SubElement(anomaly_elem, "AnomalyType").text = anomaly.anomaly_type
    ET.SubElement(anomaly_elem, "SeverityLevel").text = anomaly.severity_level
    ET.SubElement(anomaly_elem, "DeviationPercentage").text = str(anomaly.deviation_percentage) if anomaly.deviation_percentage else ""
    ET.SubElement(anomaly_elem, "ExpectedValue").text = str(anomaly.expected_value) if anomaly.expected_value else ""
    ET.SubElement(anomaly_elem, "ActualValue").text = str(anomaly.actual_value) if anomaly.actual_value else ""
    ET.SubElement(anomaly_elem, "Description").text = anomaly.description or ""
    
    # Consumption analysis
    analysis_elem = ET.SubElement(root, "ConsumptionAnalysis")
    if anomaly.actual_value and anomaly.expected_value:
        excess = anomaly.actual_value - anomaly.expected_value
        ET.SubElement(analysis_elem, "ExcessConsumption").text = str(float(excess))
    
    # Historical data (optional)
    if include_history and historical_data:
        history_elem = ET.SubElement(root, "HistoricalConsumption")
        for reading in historical_data[-10:]:  # Last 10 readings
            reading_elem = ET.SubElement(history_elem, "Reading")
            reading_elem.set("timestamp", reading['timestamp'])
            reading_elem.set("value", str(reading['value']))
            reading_elem.set("unit", reading['unit'])
    
    # Subsidy request
    request_elem = ET.SubElement(root, "SubsidyRequest")
    ET.SubElement(request_elem, "RequestType").text = "investigation_and_subsidy"
    ET.SubElement(request_elem, "Reason").text = f"Unusual {anomaly.anomaly_type} detected"
    
    # Pretty print XML
    xml_str = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ")


def send_report_to_endpoint(report_data: Any, endpoint: str, 
                           report_format: str = "JSON") -> Dict[str, Any]:
    """
    Send the report to a utility provider's endpoint.
    
    In production, this would make an HTTP request or send an email.
    For now, it simulates the sending process.
    
    Args:
        report_data: The report data (dict or XML string)
        endpoint: Email address or API URL
        recipient_endpoint
        report_format: Format of the report
    
    Returns:
        Result of the send operation
    """
    logger.info(f"Sending {report_format} report to {endpoint}")
    
    # Simulate sending (in production, use requests library or smtplib)
    try:
        # Placeholder for actual implementation
        # For HTTP endpoint:
        # response = requests.post(endpoint, json=report_data, timeout=30)
        # response.raise_for_status()
        
        # For email:
        # send_email(endpoint, subject="Subsidy Application Report", body=report_data)
        
        result = {
            "success": True,
            "sent_at": datetime.utcnow().isoformat(),
            "endpoint": endpoint,
            "format": report_format,
            "message": f"Report successfully sent to {endpoint}"
        }
        
        logger.info(f"Report sent successfully to {endpoint}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to send report: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "endpoint": endpoint
        }


def generate_and_send_subsidy_report(db: Session, anomaly_id: UUID,
                                    recipient_endpoint: str,
                                    report_format: str = "JSON",
                                    include_history: bool = True,
                                    days_of_history: int = 30) -> Dict[str, Any]:
    """
    Main function to generate and send a subsidy report.
    
    This is called when a significant anomaly is detected that may qualify
    for a utility subsidy or investigation.
    
    Args:
        db: Database session
        anomaly_id: UUID of the anomaly triggering the report
        recipient_endpoint: Email or API endpoint of utility provider
        report_format: JSON or XML
        include_history: Whether to include historical consumption data
        days_of_history: Number of days of historical data to include
    
    Returns:
        Report generation and sending result
    """
    logger.info(f"Generating subsidy report for anomaly {anomaly_id}")
    
    # Fetch anomaly details
    anomaly_data = fetch_anomaly_details(db, anomaly_id)
    
    # Fetch historical data if requested
    historical_data = []
    if include_history:
        historical_data = fetch_historical_consumption(
            db, 
            anomaly_data['meter'].meter_id,
            days_of_history
        )
    
    # Generate report based on format
    if report_format.upper() == "XML":
        report_content = generate_xml_report(anomaly_data, historical_data, include_history)
    else:
        report_content = generate_json_report(anomaly_data, historical_data, include_history)
    
    # Create subsidy report record
    subsidy_report = SubsidyReport(
        anomaly_id=anomaly_id,
        property_id=anomaly_data['property'].property_id,
        meter_id=anomaly_data['meter'].meter_id,
        report_format=report_format.upper(),
        report_data=report_content if isinstance(report_content, dict) else json.loads(json.dumps(report_content)) if report_format.upper() == "JSON" else {"xml": report_content},
        recipient_endpoint=recipient_endpoint,
        status="pending"
    )
    
    db.add(subsidy_report)
    db.commit()
    db.refresh(subsidy_report)
    
    # Send the report
    send_result = send_report_to_endpoint(report_content, recipient_endpoint, report_format)
    
    # Update subsidy report status
    if send_result.get("success"):
        subsidy_report.status = "sent"
        subsidy_report.sent_at = datetime.utcnow()
        subsidy_report.response_data = send_result
        
        # Update anomaly record
        anomaly = db.query(Anomaly).filter(Anomaly.anomaly_id == anomaly_id).first()
        anomaly.subsidy_report_sent = True
        anomaly.subsidy_report_id = str(subsidy_report.report_id)
    else:
        subsidy_report.status = "failed"
        subsidy_report.response_data = {"error": send_result.get("error")}
    
    db.commit()
    
    logger.info(f"Subsidy report {subsidy_report.report_id} generated and sent")
    
    return {
        "report_id": str(subsidy_report.report_id),
        "status": subsidy_report.status,
        "sent_at": subsidy_report.sent_at.isoformat() if subsidy_report.sent_at else None,
        "recipient_endpoint": recipient_endpoint,
        "report_format": report_format
    }


def check_and_trigger_subsidy_reports(db: Session) -> int:
    """
    Background task to check for anomalies that should trigger subsidy reports.
    
    Criteria for automatic subsidy report:
    - Severity level is 'high' or 'critical'
    - Deviation percentage > 100%
    - Continuous high consumption over weekend/holiday
    - Anomaly not yet resolved and no report sent
    
    Args:
        db: Database session
    
    Returns:
        Number of reports triggered
    """
    from datetime import date
    
    # Query for qualifying anomalies
    qualifying_anomalies = db.query(Anomaly).filter(
        Anomaly.is_resolved == False,
        Anomaly.subsidy_report_sent == False,
        Anomaly.severity_level.in_(['high', 'critical']),
        Anomaly.deviation_percentage != None,
        Anomaly.deviation_percentage > 100
    ).all()
    
    reports_triggered = 0
    
    for anomaly in qualifying_anomalies:
        try:
            # Get property to find utility provider endpoint
            meter = db.query(Meter).filter(Meter.meter_id == anomaly.meter_id).first()
            property_obj = db.query(Property).filter(Property.property_id == meter.property_id).first()
            
            # In production, this would come from configuration
            # For now, use a placeholder endpoint
            utility_provider_endpoint = os.getenv(
                f"UTILITY_PROVIDER_ENDPOINT_{property_obj.city.upper()}",
                "subsidy@utility-provider.example.com"
            )
            
            # Generate and send report
            generate_and_send_subsidy_report(
                db=db,
                anomaly_id=anomaly.anomaly_id,
                recipient_endpoint=utility_provider_endpoint,
                report_format="JSON",
                include_history=True,
                days_of_history=30
            )
            
            reports_triggered += 1
            logger.info(f"Triggered subsidy report for anomaly {anomaly.anomaly_id}")
            
        except Exception as e:
            logger.error(f"Failed to trigger subsidy report for anomaly {anomaly.anomaly_id}: {str(e)}")
    
    return reports_triggered


if __name__ == "__main__":
    print("Subsidy automation module loaded successfully")
