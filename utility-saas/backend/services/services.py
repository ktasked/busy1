"""
Business Logic Services for Utility Monitoring SaaS
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.models import (
    MeterReading, Meter, Property, Anomaly, 
    HourlySummary, DailySummary, MonthlySummary,
    SubsidyReport, UtilityType
)

logger = logging.getLogger(__name__)


class ReadingService:
    """Service for handling meter readings"""
    
    @staticmethod
    def create_reading(db: Session, reading_data: Dict[str, Any]) -> MeterReading:
        """Create a single meter reading"""
        db_reading = MeterReading(**reading_data)
        db.add(db_reading)
        db.commit()
        db.refresh(db_reading)
        return db_reading
    
    @staticmethod
    def batch_create_readings(db: Session, readings_data: List[Dict[str, Any]]) -> List[MeterReading]:
        """Create multiple meter readings in batch"""
        db_readings = [MeterReading(**data) for data in readings_data]
        db.add_all(db_readings)
        db.commit()
        for reading in db_readings:
            db.refresh(reading)
        return db_readings
    
    @staticmethod
    def get_readings_by_meter(
        db: Session, 
        meter_id: str, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[MeterReading]:
        """Get readings for a specific meter with optional time range"""
        query = db.query(MeterReading).filter(MeterReading.meter_id == meter_id)
        
        if start_time:
            query = query.filter(MeterReading.timestamp >= start_time)
        if end_time:
            query = query.filter(MeterReading.timestamp <= end_time)
        
        return query.order_by(MeterReading.timestamp.desc()).limit(limit).all()


class AggregationService:
    """Service for aggregating raw readings into summaries"""
    
    @staticmethod
    def aggregate_hourly(db: Session, meter_id: Optional[str] = None, target_date: Optional[date] = None):
        """Aggregate raw readings into hourly summaries"""
        if target_date is None:
            target_date = date.today() - timedelta(days=1)  # Aggregate yesterday's data
        
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = start_datetime + timedelta(days=1)
        
        query = db.query(
            MeterReading.meter_id,
            func.date_trunc('hour', MeterReading.timestamp).label('hour_start'),
            func.sum(MeterReading.value).label('total_consumption'),
            func.avg(MeterReading.value).label('average_consumption'),
            func.min(MeterReading.value).label('min_consumption'),
            func.max(MeterReading.value).label('max_consumption'),
            func.count().label('reading_count')
        ).filter(
            MeterReading.timestamp >= start_datetime,
            MeterReading.timestamp < end_datetime
        )
        
        if meter_id:
            query = query.filter(MeterReading.meter_id == meter_id)
        
        hourly_data = query.group_by(
            MeterReading.meter_id,
            func.date_trunc('hour', MeterReading.timestamp)
        ).all()
        
        for data in hourly_data:
            # Get price per unit
            meter = db.query(Meter).filter(Meter.meter_id == data.meter_id).first()
            if meter:
                utility_type = db.query(UtilityType).filter(
                    UtilityType.utility_type_id == meter.utility_type_id
                ).first()
                price = float(utility_type.price_per_unit) if utility_type else 0.0
                cost = float(data.total_consumption) * price
            else:
                cost = 0.0
            
            summary = HourlySummary(
                meter_id=data.meter_id,
                hour_start=data.hour_start,
                total_consumption=data.total_consumption,
                average_consumption=data.average_consumption,
                min_consumption=data.min_consumption,
                max_consumption=data.max_consumption,
                reading_count=data.reading_count,
                cost=cost
            )
            
            # Upsert (update if exists, insert if not)
            db.merge(summary)
        
        db.commit()
        logger.info(f"Aggregated {len(hourly_data)} hourly summaries for {target_date}")
    
    @staticmethod
    def aggregate_daily(db: Session, meter_id: Optional[str] = None, target_date: Optional[date] = None):
        """Aggregate hourly summaries into daily summaries"""
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        query = db.query(
            HourlySummary.meter_id,
            func.date_trunc('day', HourlySummary.hour_start).label('date'),
            func.sum(HourlySummary.total_consumption).label('total_consumption'),
            func.avg(HourlySummary.average_consumption).label('average_consumption'),
            func.min(HourlySummary.min_consumption).label('min_consumption'),
            func.max(HourlySummary.max_consumption).label('max_consumption'),
            func.sum(HourlySummary.reading_count).label('reading_count'),
            func.sum(HourlySummary.cost).label('total_cost')
        ).filter(
            func.date_trunc('day', HourlySummary.hour_start) == target_date
        )
        
        if meter_id:
            query = query.filter(HourlySummary.meter_id == meter_id)
        
        daily_data = query.group_by(
            HourlySummary.meter_id,
            func.date_trunc('day', HourlySummary.hour_start)
        ).all()
        
        for data in daily_data:
            summary = DailySummary(
                meter_id=data.meter_id,
                date=data.date,
                total_consumption=data.total_consumption,
                average_consumption=data.average_consumption,
                min_consumption=data.min_consumption,
                max_consumption=data.max_consumption,
                reading_count=data.reading_count,
                cost=data.total_cost
            )
            db.merge(summary)
        
        db.commit()
        logger.info(f"Aggregated {len(daily_data)} daily summaries for {target_date}")
    
    @staticmethod
    def aggregate_monthly(db: Session, meter_id: Optional[str] = None, year: Optional[int] = None, month: Optional[int] = None):
        """Aggregate daily summaries into monthly summaries"""
        if year is None or month is None:
            last_month = date.today() - timedelta(days=1)
            year = last_month.year
            month = last_month.month
        
        query = db.query(
            DailySummary.meter_id,
            func.extract('year', DailySummary.date).label('year'),
            func.extract('month', DailySummary.date).label('month'),
            func.sum(DailySummary.total_consumption).label('total_consumption'),
            func.avg(DailySummary.total_consumption).label('average_daily_consumption'),
            func.min(DailySummary.total_consumption).label('min_daily_consumption'),
            func.max(DailySummary.total_consumption).label('max_daily_consumption'),
            func.sum(DailySummary.reading_count).label('reading_count'),
            func.sum(DailySummary.cost).label('total_cost')
        ).filter(
            func.extract('year', DailySummary.date) == year,
            func.extract('month', DailySummary.date) == month
        )
        
        if meter_id:
            query = query.filter(DailySummary.meter_id == meter_id)
        
        monthly_data = query.group_by(
            DailySummary.meter_id,
            func.extract('year', DailySummary.date),
            func.extract('month', DailySummary.date)
        ).all()
        
        for data in monthly_data:
            summary = MonthlySummary(
                meter_id=data.meter_id,
                year=int(data.year),
                month=int(data.month),
                total_consumption=data.total_consumption,
                average_daily_consumption=data.average_daily_consumption,
                min_daily_consumption=data.min_daily_consumption,
                max_daily_consumption=data.max_daily_consumption,
                reading_count=data.reading_count,
                cost=data.total_cost
            )
            db.merge(summary)
        
        db.commit()
        logger.info(f"Aggregated {len(monthly_data)} monthly summaries for {year}-{month:02d}")


class DashboardService:
    """Service for dashboard data"""
    
    @staticmethod
    def get_dashboard_data(db: Session, property_id: str) -> Dict[str, Any]:
        """Get comprehensive dashboard data for a property"""
        property_obj = db.query(Property).filter(Property.property_id == property_id).first()
        if not property_obj:
            raise ValueError(f"Property {property_id} not found")
        
        # Get active meters
        meters = db.query(Meter).filter(
            Meter.property_id == property_id,
            Meter.is_active == True
        ).all()
        
        meter_ids = [str(m.meter_id) for m in meters]
        
        # Get current month consumption
        current_month_start = date.today().replace(day=1)
        daily_summaries = db.query(DailySummary).filter(
            DailySummary.meter_id.in_(meter_ids),
            DailySummary.date >= current_month_start
        ).all()
        
        total_consumption = sum(float(ds.total_consumption) for ds in daily_summaries)
        total_cost = sum(float(ds.cost) if ds.cost else 0.0 for ds in daily_summaries)
        
        # Get active anomalies
        active_anomalies = db.query(Anomaly).filter(
            Anomaly.meter_id.in_(meter_ids),
            Anomaly.is_resolved == False
        ).order_by(Anomaly.detected_at.desc()).limit(10).all()
        
        # Calculate baseline (previous month)
        if current_month_start.month == 1:
            prev_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
        else:
            prev_month_start = current_month_start.replace(month=current_month_start.month - 1)
        
        prev_month_summaries = db.query(DailySummary).filter(
            DailySummary.meter_id.in_(meter_ids),
            DailySummary.date >= prev_month_start,
            DailySummary.date < current_month_start
        ).all()
        
        prev_month_cost = sum(float(ds.cost) if ds.cost else 0.0 for ds in prev_month_summaries)
        cost_savings = max(0, prev_month_cost - total_cost)
        savings_percentage = (cost_savings / prev_month_cost * 100) if prev_month_cost > 0 else 0.0
        
        return {
            "property_id": str(property_obj.property_id),
            "property_name": property_obj.name,
            "summary": {
                "total_consumption": round(total_consumption, 2),
                "total_cost": round(total_cost, 2),
                "cost_savings": round(cost_savings, 2),
                "savings_percentage": round(savings_percentage, 2),
                "active_anomalies": len(active_anomalies),
                "total_meters": len(meters)
            },
            "recent_anomalies": [
                {
                    "anomaly_id": str(a.anomaly_id),
                    "meter_id": str(a.meter_id),
                    "detected_at": a.detected_at.isoformat(),
                    "anomaly_type": a.anomaly_type,
                    "severity": a.severity,
                    "deviation_percentage": float(a.deviation_percentage),
                    "expected_value": float(a.expected_value) if a.expected_value else None,
                    "actual_value": float(a.actual_value),
                    "description": a.description,
                    "is_resolved": a.is_resolved
                }
                for a in active_anomalies
            ]
        }
