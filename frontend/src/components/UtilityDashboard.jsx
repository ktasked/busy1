import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { AlertTriangle, TrendingUp, DollarSign, Zap, Droplet, Thermometer } from 'lucide-react';

/**
 * Utility Monitoring Dashboard Component
 * 
 * Displays:
 * - Real-time consumption vs predicted consumption (line chart)
 * - Detected anomalies list with details
 * - Cost savings summary card
 * 
 * @param {string} propertyId - The property ID to display data for
 * @param {string} meterId - Optional specific meter ID to focus on
 */
const UtilityDashboard = ({ propertyId, meterId = null }) => {
  // State management
  const [consumptionData, setConsumptionData] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [summary, setSummary] = useState(null);
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedUtilityType, setSelectedUtilityType] = useState('electricity');
  const [timeRange, setTimeRange] = useState('24h');

  // API base URL from environment
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

  /**
   * Fetch dashboard data on component mount
   */
  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 300000); // Refresh every 5 minutes
    return () => clearInterval(interval);
  }, [propertyId, meterId, selectedUtilityType]);

  /**
   * Fetch all dashboard data
   */
  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      
      // Fetch property summary
      const summaryResponse = await fetch(`${API_BASE_URL}/dashboard/property/${propertyId}`);
      if (summaryResponse.ok) {
        const summaryData = await summaryResponse.json();
        setSummary(summaryData);
      }

      // Fetch cost savings
      const savingsResponse = await fetch(`${API_BASE_URL}/dashboard/savings/${propertyId}`);
      if (savingsResponse.ok) {
        const savingsData = await savingsResponse.json();
        setSummary(prev => ({ ...prev, ...savingsData }));
      }

      // Fetch active anomalies
      const anomaliesResponse = await fetch(
        `${API_BASE_URL}/dashboard/anomalies?property_id=${propertyId}&limit=20`
      );
      if (anomaliesResponse.ok) {
        const anomaliesData = await anomaliesResponse.json();
        setAnomalies(anomaliesData);
      }

      // Fetch consumption data for chart
      await fetchConsumptionData();

      // Fetch forecast data
      if (meterId) {
        await fetchForecastData();
      }

      setError(null);
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
      setError('Failed to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Fetch real-time and historical consumption data
   */
  const fetchConsumptionData = async () => {
    try {
      // In production, replace with actual API endpoint
      // For demo, generate sample data
      const sampleData = generateSampleConsumptionData();
      setConsumptionData(sampleData);
    } catch (err) {
      console.error('Error fetching consumption data:', err);
    }
  };

  /**
   * Fetch ML forecast data
   */
  const fetchForecastData = async () => {
    try {
      const forecastResponse = await fetch(`${API_BASE_URL}/forecast/${meterId}?days=30`);
      if (forecastResponse.ok) {
        const forecastData = await forecastResponse.json();
        setForecast(forecastData.data_points || []);
      }
    } catch (err) {
      console.error('Error fetching forecast:', err);
    }
  };

  /**
   * Generate sample consumption data for demonstration
   * Replace with actual API calls in production
   */
  const generateSampleConsumptionData = () => {
    const now = new Date();
    const data = [];
    
    for (let i = 24; i >= 0; i--) {
      const timestamp = new Date(now.getTime() - i * 60 * 60 * 1000);
      const hour = timestamp.getHours();
      
      // Simulate realistic consumption pattern
      const baseConsumption = selectedUtilityType === 'electricity' ? 100 : 
                             selectedUtilityType === 'water' ? 50 : 80;
      const peakMultiplier = (hour >= 8 && hour <= 18) ? 1.5 : 0.7;
      const randomVariation = Math.random() * 20 - 10;
      
      const actual = baseConsumption * peakMultiplier + randomVariation;
      const predicted = baseConsumption * peakMultiplier;
      
      data.push({
        timestamp: timestamp.toISOString(),
        time: timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        actual: parseFloat(actual.toFixed(2)),
        predicted: parseFloat(predicted.toFixed(2)),
        unit: selectedUtilityType === 'electricity' ? 'kWh' : 
              selectedUtilityType === 'water' ? 'gallons' : 'BTU'
      });
    }
    
    return data;
  };

  /**
   * Format currency value
   */
  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value);
  };

  /**
   * Get severity color for anomalies
   */
  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return '#ef4444'; // red-500
      case 'high': return '#f97316'; // orange-500
      case 'medium': return '#eab308'; // yellow-500
      case 'low': return '#22c55e'; // green-500
      default: return '#6b7280'; // gray-500
    }
  };

  /**
   * Handle anomaly resolution
   */
  const handleResolveAnomaly = async (anomalyId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/anomalies/${anomalyId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (response.ok) {
        setAnomalies(prev => prev.filter(a => a.anomaly_id !== anomalyId));
      }
    } catch (err) {
      console.error('Error resolving anomaly:', err);
    }
  };

  /**
   * Handle generating subsidy report for an anomaly
   */
  const handleGenerateSubsidyReport = async (anomalyId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/subsidy/generate-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          anomaly_id: anomalyId,
          recipient_endpoint: 'subsidy@utility-provider.example.com',
          report_format: 'JSON',
          include_historical_data: true,
          days_of_history: 30
        })
      });
      
      if (response.ok) {
        alert('Subsidy report generated and sent successfully!');
      } else {
        alert('Failed to generate subsidy report.');
      }
    } catch (err) {
      console.error('Error generating subsidy report:', err);
      alert('Error generating subsidy report.');
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Utility Monitoring Dashboard</h1>
        <div className="flex space-x-2">
          <select
            value={selectedUtilityType}
            onChange={(e) => setSelectedUtilityType(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md bg-white"
          >
            <option value="electricity">Electricity</option>
            <option value="water">Water</option>
            <option value="heat">Heat</option>
          </select>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md bg-white"
          >
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Consumption Card */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Consumption Today</p>
              <p className="text-2xl font-bold text-gray-900">
                {summary?.total_consumption_today?.toFixed(1) || '0'} {selectedUtilityType === 'electricity' ? 'kWh' : selectedUtilityType === 'water' ? 'gal' : 'BTU'}
              </p>
            </div>
            <div className="p-3 bg-blue-100 rounded-full">
              {selectedUtilityType === 'electricity' ? (
                <Zap className="h-6 w-6 text-blue-600" />
              ) : selectedUtilityType === 'water' ? (
                <Droplet className="h-6 w-6 text-blue-600" />
              ) : (
                <Thermometer className="h-6 w-6 text-blue-600" />
              )}
            </div>
          </div>
        </div>

        {/* Total Cost Card */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Cost Today</p>
              <p className="text-2xl font-bold text-gray-900">
                {formatCurrency(summary?.total_cost_today || 0)}
              </p>
            </div>
            <div className="p-3 bg-green-100 rounded-full">
              <DollarSign className="h-6 w-6 text-green-600" />
            </div>
          </div>
        </div>

        {/* Cost Savings Card */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Cost Savings (vs Baseline)</p>
              <p className="text-2xl font-bold text-green-600">
                {formatCurrency(summary?.savings || 0)}
              </p>
              <p className={`text-sm ${summary?.savings_percentage >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {summary?.savings_percentage >= 0 ? '+' : ''}{summary?.savings_percentage?.toFixed(1)}%
              </p>
            </div>
            <div className="p-3 bg-green-100 rounded-full">
              <TrendingUp className="h-6 w-6 text-green-600" />
            </div>
          </div>
        </div>

        {/* Active Anomalies Card */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Active Anomalies</p>
              <p className="text-2xl font-bold text-gray-900">{anomalies.length}</p>
              <p className="text-sm text-gray-500">Require attention</p>
            </div>
            <div className="p-3 bg-red-100 rounded-full">
              <AlertTriangle className="h-6 w-6 text-red-600" />
            </div>
          </div>
        </div>
      </div>

      {/* Main Chart - Real-time vs Predicted Consumption */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Consumption: Real-time vs Predicted
        </h2>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={consumptionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis 
                dataKey="time" 
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
                label={{ 
                  value: selectedUtilityType === 'electricity' ? 'kWh' : selectedUtilityType === 'water' ? 'Gallons' : 'BTU', 
                  angle: -90, 
                  position: 'insideLeft' 
                }}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#fff', 
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                }}
              />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="actual" 
                stroke="#3b82f6" 
                strokeWidth={2}
                dot={false}
                name="Actual Consumption"
              />
              <Line 
                type="monotone" 
                dataKey="predicted" 
                stroke="#10b981" 
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                name="Predicted Consumption"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Two-column layout for anomalies and forecast */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Anomalies List */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Detected Anomalies
          </h2>
          {anomalies.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <AlertTriangle className="h-12 w-12 mx-auto mb-2 text-gray-400" />
              <p>No active anomalies detected</p>
            </div>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {anomalies.map((anomaly) => (
                <div 
                  key={anomaly.anomaly_id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center space-x-2">
                      <div 
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: getSeverityColor(anomaly.severity_level) }}
                      />
                      <span className="font-medium text-gray-900">
                        {anomaly.anomaly_type}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {new Date(anomaly.detection_timestamp).toLocaleString()}
                    </span>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-2 text-sm mb-3">
                    <div>
                      <span className="text-gray-600">Meter:</span>
                      <span className="ml-2 font-mono text-gray-900">
                        {anomaly.meter_id.substring(0, 8)}...
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-600">Deviation:</span>
                      <span className={`ml-2 font-medium ${
                        anomaly.deviation_percentage > 100 ? 'text-red-600' : 'text-orange-600'
                      }`}>
                        {anomaly.deviation_percentage?.toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-600">Expected:</span>
                      <span className="ml-2 text-gray-900">{anomaly.expected_value?.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Actual:</span>
                      <span className="ml-2 text-gray-900">{anomaly.actual_value?.toFixed(2)}</span>
                    </div>
                  </div>
                  
                  <p className="text-sm text-gray-600 mb-3">{anomaly.description}</p>
                  
                  <div className="flex space-x-2">
                    <button
                      onClick={() => handleResolveAnomaly(anomaly.anomaly_id)}
                      className="px-3 py-1 text-sm bg-green-100 text-green-700 rounded-md hover:bg-green-200 transition-colors"
                    >
                      Mark Resolved
                    </button>
                    {(anomaly.severity_level === 'high' || anomaly.severity_level === 'critical') && (
                      <button
                        onClick={() => handleGenerateSubsidyReport(anomaly.anomaly_id)}
                        className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded-md hover:bg-blue-200 transition-colors"
                      >
                        Generate Subsidy Report
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Forecast Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            30-Day Consumption Forecast
          </h2>
          {forecast.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <p>No forecast data available</p>
              <p className="text-sm mt-1">Select a specific meter to view forecast</p>
            </div>
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={forecast}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis 
                    dataKey={(d) => new Date(d.timestamp).toLocaleDateString()}
                    stroke="#6b7280"
                    tick={{ fontSize: 10 }}
                    angle={-45}
                    textAnchor="end"
                  />
                  <YAxis 
                    stroke="#6b7280"
                    tick={{ fontSize: 12 }}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#fff', 
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px'
                    }}
                    labelFormatter={(label) => `Date: ${label}`}
                  />
                  <Legend />
                  <Area 
                    type="monotone" 
                    dataKey="predicted_value" 
                    stroke="#8b5cf6" 
                    fill="#8b5cf6"
                    fillOpacity={0.3}
                    name="Predicted"
                  />
                  <Area 
                    type="monotone" 
                    dataKey="upper_bound" 
                    stroke="#a78bfa" 
                    fill="#a78bfa"
                    fillOpacity={0.1}
                    name="Upper Bound"
                    strokeDasharray="3 3"
                  />
                  <Area 
                    type="monotone" 
                    dataKey="lower_bound" 
                    stroke="#a78bfa" 
                    fill="#a78bfa"
                    fillOpacity={0.1}
                    name="Lower Bound"
                    strokeDasharray="3 3"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
          
          {forecast.length > 0 && (
            <div className="mt-4 p-4 bg-purple-50 rounded-lg">
              <div className="flex justify-between items-center">
                <div>
                  <p className="text-sm text-gray-600">Total Predicted Consumption</p>
                  <p className="text-xl font-bold text-purple-700">
                    {forecast.reduce((sum, d) => sum + d.predicted_value, 0).toFixed(1)} units
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-600">Model Accuracy</p>
                  <p className="text-xl font-bold text-purple-700">
                    {forecast.model_accuracy || 'N/A'}%
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UtilityDashboard;
