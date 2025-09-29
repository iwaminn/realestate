import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  SelectChangeEvent,
  Chip,
  Paper,
  CircularProgress,
  Pagination,
  Stack,
} from '@mui/material';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,

} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';
import axios from '../utils/axiosConfig';

// Chart.js の登録
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

interface TransactionData {
  id: number;
  area_name: string;
  transaction_price: number;
  price_per_sqm: number | null;
  floor_area: number | null;
  transaction_year: number;
  transaction_quarter: number;
  nearest_station: string | null;
  station_distance: number | null;
}

interface AreaStatistics {
  area_name: string;
  avg_price_per_sqm: number;
  median_price_per_sqm: number;
  transaction_count: number;
  avg_transaction_price: number;
  min_price: number;
  max_price: number;
}

interface PriceTrendData {
  year: number;
  quarter: number;
  avg_price_per_sqm: number;
  transaction_count: number;
}

type OrderBy = 'transaction_year' | 'area_name' | 'transaction_price' | 'price_per_sqm' | 'floor_area' | 'station_distance';
type Order = 'asc' | 'desc';

const TransactionPricesPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [areas, setAreas] = useState<string[]>([]);
  const [selectedArea, setSelectedArea] = useState<string>('');
  const [selectedYear, setSelectedYear] = useState<number | ''>('');
  const [startYear, setStartYear] = useState<number>(2020);
  const [startQuarter, setStartQuarter] = useState<number>(1);
  const [endYear, setEndYear] = useState<number>(2025);
  const [endQuarter, setEndQuarter] = useState<number>(1);
  const [areaStats, setAreaStats] = useState<AreaStatistics[]>([]);
  const [priceTrends, setPriceTrends] = useState<PriceTrendData[]>([]);
  const [areaSpecificTrends, setAreaSpecificTrends] = useState<{[key: string]: PriceTrendData[]}>({});
  const [transactions, setTransactions] = useState<TransactionData[]>([]);
  const [sizeTrends, setSizeTrends] = useState<any[]>([]);
  const [ageTrends, setAgeTrends] = useState<any[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [rowsPerPage] = useState<number>(50);
  const [orderBy, setOrderBy] = useState<OrderBy>('transaction_year');
  const [order, setOrder] = useState<Order>('desc');

  // 並び替えハンドラー
  const handleRequestSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
    setCurrentPage(1); // 並び替え時はページを1に戻す
  };

  // エリア一覧を取得
  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const response = await axios.get('/api/transaction-prices/areas');
        setAreas(response.data);
      } catch (error) {
        console.error('エリア取得エラー:', error);
      }
    };
    fetchAreas();
  }, []);

  // データを取得
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        // エリア統計
        const statsParams: any = {};
        if (selectedYear) statsParams.year = selectedYear;

        const [statsRes, trendsRes, transactionsRes, sizeTrendsRes, ageTrendsRes] = await Promise.all([
          axios.get('/api/transaction-prices/statistics/by-area', { params: statsParams }),
          axios.get('/api/transaction-prices/trends', {
            params: selectedArea ? { area: selectedArea } : {}
          }),
          axios.get('/api/transaction-prices/transactions', {
            params: {
              ...(selectedArea && { area: selectedArea }),
              ...(selectedYear && { year: selectedYear }),
            }
          }),
          axios.get('/api/transaction-prices/trends-by-size'),
          axios.get('/api/transaction-prices/trends-by-age')
        ]);

        setAreaStats(statsRes.data);
        setPriceTrends(trendsRes.data);
        setTransactions(transactionsRes.data);
        setSizeTrends(sizeTrendsRes.data);
        setAgeTrends(ageTrendsRes.data);

        // 上位5エリアの時系列データを取得
        if (statsRes.data.length > 0 && !selectedArea) {
          const topAreaNames = statsRes.data.slice(0, 5).map((s: AreaStatistics) => s.area_name);
          const areaPromises = topAreaNames.map((area: string) =>
            axios.get('/api/transaction-prices/trends', { params: { area } })
          );

          const areaResults = await Promise.all(areaPromises);
          const trendsMap: {[key: string]: PriceTrendData[]} = {};

          topAreaNames.forEach((area: string, index: number) => {
            trendsMap[area] = areaResults[index].data;
          });

          setAreaSpecificTrends(trendsMap);
        }
      } catch (error) {
        console.error('データ取得エラー:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [selectedArea, selectedYear, startYear, startQuarter, endYear, endQuarter]);

  // エリア選択ハンドラー
  const handleAreaChange = (event: SelectChangeEvent<string>) => {
    setSelectedArea(event.target.value);
  };

  // 年選択ハンドラー
  const handleYearChange = (event: SelectChangeEvent<number | ''>) => {
    setSelectedYear(event.target.value as number | '');
  };

  // 期間選択ハンドラー
  const handleStartYearChange = (event: SelectChangeEvent<number>) => {
    const newStartYear = event.target.value as number;
    setStartYear(newStartYear);
    
    // 開始年が終了年より後の場合、終了年を調整
    if (newStartYear > endYear) {
      setEndYear(newStartYear);
      setEndQuarter(startQuarter);
    } else if (newStartYear === endYear && startQuarter > endQuarter) {
      setEndQuarter(startQuarter);
    }
  };

  const handleStartQuarterChange = (event: SelectChangeEvent<number>) => {
    const newStartQuarter = event.target.value as number;
    setStartQuarter(newStartQuarter);
    
    // 同じ年で開始四半期が終了四半期より後の場合、終了四半期を調整
    if (startYear === endYear && newStartQuarter > endQuarter) {
      setEndQuarter(newStartQuarter);
    }
  };

  const handleEndYearChange = (event: SelectChangeEvent<number>) => {
    const newEndYear = event.target.value as number;
    setEndYear(newEndYear);
    
    // 終了年が開始年より前の場合、開始年を調整
    if (newEndYear < startYear) {
      setStartYear(newEndYear);
      setStartQuarter(endQuarter);
    } else if (newEndYear === startYear && endQuarter < startQuarter) {
      setStartQuarter(endQuarter);
    }
  };

  const handleEndQuarterChange = (event: SelectChangeEvent<number>) => {
    const newEndQuarter = event.target.value as number;
    setEndQuarter(newEndQuarter);
    
    // 同じ年で終了四半期が開始四半期より前の場合、開始四半期を調整
    if (startYear === endYear && newEndQuarter < startQuarter) {
      setStartQuarter(newEndQuarter);
    }
  };

  // 期間でデータをフィルタリング
  const filterByPeriod = (data: any[]) => {

    return data.filter(d => {
      const dYear = d.year || d.transaction_year;
      const dQuarter = d.quarter || d.transaction_quarter;
      
      if (!dYear || !dQuarter) return false;

      const startValue = startYear * 4 + startQuarter;
      const endValue = endYear * 4 + endQuarter;
      const dataValue = dYear * 4 + dQuarter;

      return dataValue >= startValue && dataValue <= endValue;
    });
  };

  // フィルタリング済みデータ
  const filteredPriceTrends = filterByPeriod(priceTrends);
  const filteredTransactions = filterByPeriod(transactions);
  const filteredSizeTrends = filterByPeriod(sizeTrends);
  const filteredAgeTrends = filterByPeriod(ageTrends);



  // ソート済みデータ
  const sortedTransactions = [...filteredTransactions].sort((a, b) => {
    let aValue: any;
    let bValue: any;

    switch (orderBy) {
      case 'transaction_year':
        aValue = a.transaction_year * 10 + a.transaction_quarter;
        bValue = b.transaction_year * 10 + b.transaction_quarter;
        break;
      case 'area_name':
        aValue = a.area_name || '';
        bValue = b.area_name || '';
        break;
      case 'transaction_price':
        aValue = a.transaction_price || 0;
        bValue = b.transaction_price || 0;
        break;
      case 'price_per_sqm':
        aValue = a.price_per_sqm || 0;
        bValue = b.price_per_sqm || 0;
        break;
      case 'floor_area':
        aValue = a.floor_area || 0;
        bValue = b.floor_area || 0;
        break;
      case 'station_distance':
        aValue = a.station_distance || 999;
        bValue = b.station_distance || 999;
        break;
      default:
        return 0;
    }

    if (order === 'asc') {
      return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
    } else {
      return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
    }
  });

  // ページング計算
  const totalPages = Math.ceil(sortedTransactions.length / rowsPerPage);
  const startIndex = (currentPage - 1) * rowsPerPage;
  const endIndex = startIndex + rowsPerPage;
  const paginatedTransactions = sortedTransactions.slice(startIndex, endIndex);



  // フィルター変更時にページをリセット
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedArea, startYear, startQuarter, endYear, endQuarter]);

  // 価格推移チャートのデータ
  const trendChartData = {
    labels: filteredPriceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: [
      {
        label: '平均価格（万円/㎡）',
        data: filteredPriceTrends.map(d => d.avg_price_per_sqm),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.5)',
        tension: 0.1,
      }
    ]
  };

  // 取引件数推移チャートのデータ
  const volumeChartData = {
    labels: filteredPriceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: [
      {
        label: '取引件数',
        data: filteredPriceTrends.map(d => d.transaction_count),
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1,
      }
    ]
  };



  // 広さ別価格推移チャート
  const sizeCategories = [...new Set(filteredSizeTrends.map(d => d.category))];
  const sizeTrendChartData = {
    labels: filteredPriceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: sizeCategories.map((category, index) => {
      const colors = [
        'rgba(255, 99, 132, 1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
        'rgba(255, 159, 64, 1)',
      ];

      const categoryTrends = filteredSizeTrends.filter(d => d.category === category);
      const dataMap = new Map(
        categoryTrends.map(t => [`${t.year}Q${t.quarter}`, t.avg_price_per_sqm])
      );

      return {
        label: category,
        data: filteredPriceTrends.map(d => {
          const key = `${d.year}Q${d.quarter}`;
          return dataMap.get(key) || null;
        }),
        borderColor: colors[index % colors.length],
        backgroundColor: colors[index % colors.length].replace('1)', '0.2)'),
        tension: 0.1,
      };
    })
  };

  // 築年別価格推移チャート
  const ageCategories = [...new Set(filteredAgeTrends.map(d => d.category))];
  const ageTrendChartData = {
    labels: filteredPriceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: ageCategories.map((category, index) => {
      const colors = [
        'rgba(255, 99, 132, 1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
      ];

      const categoryTrends = filteredAgeTrends.filter(d => d.category === category);
      const dataMap = new Map(
        categoryTrends.map(t => [`${t.year}Q${t.quarter}`, t.avg_price_per_sqm])
      );

      return {
        label: category,
        data: filteredPriceTrends.map(d => {
          const key = `${d.year}Q${d.quarter}`;
          return dataMap.get(key) || null;
        }),
        borderColor: colors[index % colors.length],
        backgroundColor: colors[index % colors.length].replace('1)', '0.2)'),
        tension: 0.1,
      };
    })
  };


  return (
    <Container maxWidth="lg">
      <Box sx={{ py: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          港区 不動産取引価格分析
        </Typography>

        {/* フィルター */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            期間を選択してください（{startYear}年Q{startQuarter} ～ {endYear}年Q{endQuarter}）
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth>
                <InputLabel>エリアを選択</InputLabel>
                <Select
                  value={selectedArea}
                  onChange={handleAreaChange}
                  label="エリアを選択"
                >
                  <MenuItem value="">全エリア</MenuItem>
                  {areas.map(area => (
                    <MenuItem key={area} value={area}>{area}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} md={3}>
              <FormControl fullWidth>
                <InputLabel>開始年</InputLabel>
                <Select
                  value={startYear}
                  onChange={handleStartYearChange}
                  label="開始年"
                >
                  {[2020, 2021, 2022, 2023, 2024, 2025]
                    .filter(year => year <= endYear)
                    .map(year => (
                      <MenuItem key={year} value={year}>{year}年</MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} md={2}>
              <FormControl fullWidth>
                <InputLabel>開始四半期</InputLabel>
                <Select
                  value={startQuarter}
                  onChange={handleStartQuarterChange}
                  label="開始四半期"
                >
                  {[1, 2, 3, 4]
                    .filter(q => startYear < endYear || q <= endQuarter)
                    .map(q => (
                      <MenuItem key={q} value={q}>第{q}四半期</MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} md={3}>
              <FormControl fullWidth>
                <InputLabel>終了年</InputLabel>
                <Select
                  value={endYear}
                  onChange={handleEndYearChange}
                  label="終了年"
                >
                  {[2020, 2021, 2022, 2023, 2024, 2025]
                    .filter(year => year >= startYear)
                    .map(year => (
                      <MenuItem key={year} value={year}>{year}年</MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} md={2}>
              <FormControl fullWidth>
                <InputLabel>終了四半期</InputLabel>
                <Select
                  value={endQuarter}
                  onChange={handleEndQuarterChange}
                  label="終了四半期"
                >
                  {[1, 2, 3, 4]
                    .filter(q => startYear < endYear || q >= startQuarter)
                    .map(q => (
                      <MenuItem key={q} value={q}>第{q}四半期</MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Paper>

        {loading ? (
          <Box display="flex" justifyContent="center" py={5}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* 価格推移チャート */}
            {filteredPriceTrends.length > 0 && (
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    価格推移
                    {selectedArea && <Chip label={selectedArea} sx={{ ml: 2 }} />}
                    <Chip label={`${startYear}年Q${startQuarter} ～ ${endYear}年Q${endQuarter}`} sx={{ ml: 1 }} size="small" />
                  </Typography>
                  <Line data={trendChartData} />
                </CardContent>
              </Card>
            )}

            {/* 取引件数推移チャート */}
            {filteredPriceTrends.length > 0 && (
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    取引件数推移
                    {selectedArea && <Chip label={selectedArea} sx={{ ml: 2 }} />}
                    <Chip label={`${startYear}年Q${startQuarter} ～ ${endYear}年Q${endQuarter}`} sx={{ ml: 1 }} size="small" />
                  </Typography>
                  <Bar data={volumeChartData} />
                </CardContent>
              </Card>
            )}



            {/* 広さ別価格推移 */}
            {sizeTrends.length > 0 && (
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    広さ別単価推移
                  </Typography>
                  <Line data={sizeTrendChartData} />
                </CardContent>
              </Card>
            )}

            {/* 築年別価格推移 */}
            {ageTrends.length > 0 && (
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    築年別単価推移
                  </Typography>
                  <Line data={ageTrendChartData} />
                </CardContent>
              </Card>
            )}



            {/* 期間別統計テーブル */}
            {filteredPriceTrends.length > 0 && (
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    期間別統計サマリー
                  </Typography>
                  <Box sx={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid #ddd' }}>
                          <th style={{ padding: '8px', textAlign: 'left' }}>期間</th>
                          <th style={{ padding: '8px', textAlign: 'right' }}>取引件数</th>
                          <th style={{ padding: '8px', textAlign: 'right' }}>平均単価<br/>（万円/㎡）</th>
                          {selectedArea && (
                            <th style={{ padding: '8px', textAlign: 'right' }}>エリア</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPriceTrends.map((trend) => (
                          <tr key={`${trend.year}-${trend.quarter}`} style={{ borderBottom: '1px solid #eee' }}>
                            <td style={{ padding: '8px' }}>{trend.year}年第{trend.quarter}四半期</td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>{trend.transaction_count}</td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>{trend.avg_price_per_sqm.toFixed(1)}</td>
                            {selectedArea && (
                              <td style={{ padding: '8px', textAlign: 'right' }}>{trend.area_name || selectedArea}</td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Box>
                </CardContent>
              </Card>
            )}

            {/* 個別取引一覧 */}
            {filteredTransactions.length > 0 && (
              <Card>
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                    <Typography variant="h6">
                      個別取引一覧（全{filteredTransactions.length}件）
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {startIndex + 1}～{Math.min(endIndex, filteredTransactions.length)}件を表示
                    </Typography>
                  </Stack>
                  
                  <Box sx={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid #ddd', backgroundColor: '#f5f5f5' }}>
                          <th style={{ padding: '8px', textAlign: 'center', minWidth: '50px' }}>No.</th>
                          <th 
                            style={{ 
                              padding: '8px', 
                              textAlign: 'left', 
                              minWidth: '100px',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('transaction_year')}
                          >
                            取引時期
                            {orderBy === 'transaction_year' && (
                              <span style={{ marginLeft: '4px' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th 
                            style={{ 
                              padding: '8px', 
                              textAlign: 'left', 
                              minWidth: '100px',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('area_name')}
                          >
                            エリア
                            {orderBy === 'area_name' && (
                              <span style={{ marginLeft: '4px' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th 
                            style={{ 
                              padding: '8px', 
                              textAlign: 'right', 
                              minWidth: '100px',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('transaction_price')}
                          >
                            取引価格<br/>（万円）
                            {orderBy === 'transaction_price' && (
                              <span style={{ marginLeft: '4px' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th 
                            style={{ 
                              padding: '8px', 
                              textAlign: 'right',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('price_per_sqm')}
                          >
                            単価<br/>（万円/㎡）
                            {orderBy === 'price_per_sqm' && (
                              <span style={{ marginLeft: '4px' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th 
                            style={{ 
                              padding: '8px', 
                              textAlign: 'right',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('floor_area')}
                          >
                            面積<br/>（㎡）
                            {orderBy === 'floor_area' && (
                              <span style={{ marginLeft: '4px' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th style={{ padding: '8px', textAlign: 'left' }}>間取り</th>
                          <th style={{ padding: '8px', textAlign: 'left' }}>最寄駅</th>
                          <th 
                            style={{ 
                              padding: '8px', 
                              textAlign: 'right',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('station_distance')}
                          >
                            駅距離<br/>（分）
                            {orderBy === 'station_distance' && (
                              <span style={{ marginLeft: '4px' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th style={{ padding: '8px', textAlign: 'left' }}>建築年</th>
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedTransactions.map((transaction, index) => (
                          <tr key={transaction.id} style={{ 
                            borderBottom: '1px solid #eee',
                            backgroundColor: index % 2 === 0 ? 'white' : '#fafafa'
                          }}>
                            <td style={{ padding: '8px', textAlign: 'center' }}>
                              {startIndex + index + 1}
                            </td>
                            <td style={{ padding: '8px' }}>
                              {transaction.transaction_year}年Q{transaction.transaction_quarter}
                            </td>
                            <td style={{ padding: '8px' }}>{transaction.area_name}</td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>
                              {transaction.transaction_price?.toLocaleString() || '-'}
                            </td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>
                              {transaction.price_per_sqm ? 
                                (transaction.price_per_sqm / 10000).toFixed(1) : '-'}
                            </td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>
                              {transaction.floor_area?.toFixed(1) || '-'}
                            </td>
                            <td style={{ padding: '8px' }}>{transaction.layout || '-'}</td>
                            <td style={{ padding: '8px' }}>{transaction.nearest_station || '-'}</td>
                            <td style={{ padding: '8px', textAlign: 'right' }}>
                              {transaction.station_distance || '-'}
                            </td>
                            <td style={{ padding: '8px' }}>{transaction.built_year || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Box>
                  
                  {totalPages > 1 && (
                    <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
                      <Pagination 
                        count={totalPages} 
                        page={currentPage} 
                        onChange={(event, value) => setCurrentPage(value)}
                        color="primary"
                        showFirstButton
                        showLastButton
                      />
                    </Box>
                  )}
                </CardContent>
              </Card>
            )}
          </>
        )}
      </Box>
    </Container>
  );
};

export default TransactionPricesPage;