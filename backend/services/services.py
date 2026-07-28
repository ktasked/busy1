"""
Services for the Utility Monitoring Platform.
Handles business logic for readings, anomalies, and reporting.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple
import logging
from uuid import UUID

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.models import (
    MeterReading, HourlySummary, DailySummary, MonthlySummary,
    Anomaly, Meter, Property, UtilityType, SubsidyReport
)

logger = logging.getLogger(__name__)


class ReadingService:
    """Service for handling meter reading operations."""

    @staticmethod
    def save_reading(db: Session, meter_id: UUID, reading_data: Dict[str, Any]) -> MeterReading:
        """Save a single meter reading to the database."""
        reading = MeterReading(
            meter_id=meter_id,
            reading_timestamp=reading_data['reading_timestamp'],
            consumption_value=reading_data['consumption_value'],
            unit_of_measurement=reading_data['unit_of_measurement'],
            reading_type=reading_data.get('reading_type', 'automatic'),
            temperature_ambient=reading_data.get('temperature_ambient'),
            humidity_percent=reading_data.get('humidity_percent'),
            voltage_level=reading_data.get('voltage_level'),
            flow_rate=reading_data.get('flow_rate')
        )
        db.add(reading)
        return reading

    @staticmethod
    def validate_reading(db: Session, meter_id: UUID, reading_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate incoming reading data."""
        # Check if meter exists and is active
        meter = db.query(Meter).filter(
            Meter.meter_id == meter_id,
            Meter.is_active == True
        ).first()
        
        if not meter:
            return False, f"Meter {meter_id} not found or inactive"
        
        # Check for duplicate reading
        existing = db.query(MeterReading).filter(
            MeterReading.meter_id == meter_id,
            MeterReading.reading_timestamp == reading_data['reading_timestamp']
        ).first()
        
        if existing:
            return False, f"Duplicate reading at {reading_data['reading_timestamp']}"
        
        # Validate consumption value is reasonable (not negative, not extremely high)
        if reading_data['consumption_value'] < 0:
            return False, "Consumption value cannot be negative"
        
        # Check for unrealistic spikes (>10x average of last 10 readings)
        recent_readings = db.query(MeterReading).filter(
            MeterReading.meter_id == meter_id
        ).order_by(MeterReading.reading_timestamp.desc()).limit(10).all()
        
        if len(recent_readings) >= 3:
            avg_recent = sum(r.consumption_value for r in recent_readings) / len(recent_readings)
            if reading_data['consumption_value'] > avg_recent * 10:
                logger.warning(f"Potential spike detected for meter {meter_id}: {reading_data['consumption_value']} vs avg {avg_recent}")
        
        return True, "Valid"


class AggregationService:
    """Service for aggregating raw readings into summaries."""

    @staticmethod
    def aggregate_hourly(db: Session, meter_id: Optional[UUID] = None, 
                        start_time: Optional[datetime] = None) -> int:
        """
        Aggregate raw readings into hourly summaries.
        Returns the number of summaries created.
        """
        if start_time is None:
            start_time = datetime.utcnow() - timedelta(hours=24)
        
        # Query raw readings grouped by hour
        query = db.query(
            MeterReading.meter_id,
            func.date_trunc('hour', MeterReading.reading_timestamp).label('hour_start'),
            func.sum(MeterReading.consumption_value).label('total_consumption'),
            func.avg(MeterReading.consumption_value).label('avg_consumption'),
            func.min(MeterReading.consumption_value).label('min_consumption'),
            func.max(MeterReading.consumption_value).label('max_consumption'),
            func.count().label('reading_count')
        ).filter(
            MeterReading.reading_timestamp >= start_time
        )
        
        if meter_id:
            query = query.filter(MeterReading.meter_id == meter_id)
        
        hourly_data = query.group_by(
            MeterReading.meter_id,
            func.date_trunc('hour', MeterReading.reading_timestamp)
        ).all()
        
        summaries_created = 0
        for row in hourly_data:
            # Get cost per unit from utility type
            meter = db.query(Meter).filter(Meter.meter_id == row.meter_id).first()
            if not meter:
                continue
            
            utility_type = db.query(UtilityType).filter(
                UtilityType.utility_type_id == meter.utility_type_id
            ).first()
            
            cost_per_unit = float(utility_type.cost_per_unit) if utility_type else 0.0
            estimated_cost = float(row.total_consumption) * cost_per_unit
            
            summary = HourlySummary(
                meter_id=row.meter_id,
                hour_start=row.hour_start,
                total_consumption=row.total_consumption,
                avg_consumption=row.avg_consumption,
                min_consumption=row.min_consumption,
                max_consumption=row.max_consumption,
                reading_count=row.reading_count,
                estimated_cost=estimated_cost
            )
            
            # Use ON CONFLICT to update existing records
            db.merge(summary)
            summaries_created += 1
        
        db.commit()
        logger.info(f"Created {summaries_created} hourly summaries")
        return summaries_created

    @staticmethod
    def aggregate_daily(db: Session, meter_id: Optional[UUID] = None,
                       start_date: Optional[date] = None) -> int:
        """Aggregate raw readings into daily summaries."""
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
        
        query = db.query(
            MeterReading.meter_id,
            func.date(MeterReading.reading_timestamp).label('summary_date'),
            func.sum(MeterReading.consumption_value).label('total_consumption'),
            func.avg(MeterReading.consumption_value).label('avg_consumption'),
            func.min(MeterReading.consumption_value).label('min_consumption'),
            func.max(MeterReading.consumption_value).label('max_consumption'),
            func.count().label('reading_count')
        ).filter(
            MeterReading.reading_timestamp >= datetime.combine(start_date, datetime.min.time())
        )
        
        if meter_id:
            query = query.filter(MeterReading.meter_id == meter_id)
        
        daily_data = query.group_by(
            MeterReading.meter_id,
            func.date(MeterReading.reading_timestamp)
        ).all()
        
        summaries_created = 0
        for row in daily_data:
            meter = db.query(Meter).filter(Meter.meter_id == row.meter_id).first()
            if not meter:
                continue
            
            utility_type = db.query(UtilityType).filter(
                UtilityType.utility_type_id == meter.utility_type_id
            ).first()
            
            cost_per_unit = float(utility_type.cost_per_unit) if utility_type else 0.0
            carbon_factor = float(utility_type.carbon_factor) if utility_type else 0.0
            
            estimated_cost = float(row.total_consumption) * cost_per_unit
            carbon_footprint = float(row.total_consumption) * carbon_factor
            
            # Find peak hour
            peak_hour_query = db.query(
                func.extract('hour', MeterReading.reading_timestamp).label('hour'),
                func.sum(MeterReading.consumption_value).label('hour_total')
            ).filter(
                MeterReading.meter_id == row.meter_id,
                func.date(MeterReading.reading_timestamp) == row.summary_date
            ).group_by(
                func.extract('hour', MeterReading.reading_timestamp)
            ).order_by(func.sum(MeterReading.consumption_value).desc()).first()
            
            peak_hour = int(peak_hour_query.hour) if peak_hour_query else None
            
            summary = DailySummary(
                meter_id=row.meter_id,
                summary_date=row.summary_date,
                total_consumption=row.total_consumption,
                avg_consumption=row.avg_consumption,
                min_consumption=row.min_consumption,
                max_consumption=row.max_consumption,
                peak_hour=peak_hour,
                reading_count=row.reading_count,
                estimated_cost=estimated_cost,
                carbon_footprint=carbon_footprint
            )
            
            db.merge(summary)
            summaries_created += 1
        
        db.commit()
        logger.info(f"Created {summaries_created} daily summaries")
        return summaries_created

    @staticmethod
    def aggregate_monthly(db: Session, meter_id: Optional[UUID] = None) -> int:
        """Aggregate daily summaries into monthly summaries."""
        # Implementation similar to daily aggregation
        # Uses first day of month as summary_month
        logger.info("Monthly aggregation called (implementation pending)")
        return 0


class DashboardService:
    """Service for dashboard data retrieval."""

    @staticmethod
    def get_property_summary(db: Session, property_id: UUID) -> Dict[str, Any]:
        """Get summary data for a property."""
        property_obj = db.query(Property).filter(
            Property.property_id == property_id
        ).first()
        
        if not property_obj:
            return {}
        
        # Get meters for this property
        meters = db.query(Meter).filter(
            Meter.property_id == property_id,
            Meter.is_active == True
        ).all()
        
        meter_ids = [m.meter_id for m in meters]
        
        # Today's consumption
        today = date.today()
        today_summaries = db.query(DailySummary).filter(
            DailySummary.meter_id.in_(meter_ids),
            DailySummary.summary_date == today
        ).all()
        
        total_consumption = sum(float(s.total_consumption) for s in today_summaries)
        total_cost = sum(float(s.estimated_cost) for s in today_summaries)
        
        # Active anomalies
        active_anomalies = db.query(Anomaly).filter(
            Anomaly.meter_id.in_(meter_ids),
            Anomaly.is_resolved == False
        ).count()
        
        return {
            "property_id": str(property_obj.property_id),
            "property_name": property_obj.property_name,
            "property_type": property_obj.property_type,
            "total_meters": len(meters),
            "total_consumption_today": total_consumption,
            "total_cost_today": total_cost,
            "anomalies_count": active_anomalies
        }

    @staticmethod
    def get_cost_savings(db: Session, property_id: UUID, 
                        baseline_days: int = 30) -> Dict[str, float]:
        """Calculate cost savings compared to baseline period."""
        today = date.today()
        baseline_start = today - timedelta(days=baseline_days)
        previous_period_start = baseline_start - timedelta(days=baseline_days)
        
        # Get all meters for property
        meters = db.query(Meter).filter(
            Meter.property_id == property_id,
            Meter.is_active == True
        ).all()
        
        meter_ids = [m.meter_id for m in meters]
        
        # Current period consumption
        current_summaries = db.query(DailySummary).filter(
            DailySummary.meter_id.in_(meter_ids),
            DailySummary.summary_date >= baseline_start,
            DailySummary.summary_date < today
        ).all()
        
        # Previous period consumption
        previous_summaries = db.query(DailySummary).filter(
            DailySummary.meter_id.in_(meter_ids),
            DailySummary.summary_date >= previous_period_start,
            DailySummary.summary_date < baseline_start
        ).all()
        
        current_cost = sum(float(s.estimated_cost) for s in current_summaries)
        previous_cost = sum(float(s.estimated_cost) for s in previous_summaries)
        
        savings = previous_cost - current_cost if previous_cost > 0 else 0
        savings_percentage = (savings / previous_cost * 100) if previous_cost > 0 else 0
        
        return {
            "current_cost": current_cost,
            "baseline_cost": previous_cost,
            "savings": savings,
            "savings_percentage": savings_percentage
        }
