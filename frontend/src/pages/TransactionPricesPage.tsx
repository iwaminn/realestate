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
  useMediaQuery,
  useTheme,
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
  layout: string | null;
  built_year: number | null;
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

type OrderBy = 'transaction_year' | 'area_name' | 'transaction_price' | 'price_per_sqm' | 'floor_area';
type Order = 'asc' | 'desc';

const TransactionPricesPage: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [loading, setLoading] = useState(false);
  const [areas, setAreas] = useState<string[]>([]);
  const [areasByDistrict, setAreasByDistrict] = useState<{[key: string]: string[]}>({});
  const [selectedDistrict, setSelectedDistrict] = useState<string>('');
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
        const [areasRes, areasByDistrictRes] = await Promise.all([
          axios.get('/api/transaction-prices/areas'),
          axios.get('/api/transaction-prices/areas-by-district')
        ]);
        setAreas(areasRes.data);
        setAreasByDistrict(areasByDistrictRes.data);
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

  // 区選択ハンドラー
  const handleDistrictChange = (event: SelectChangeEvent<string>) => {
    setSelectedDistrict(event.target.value);
    setSelectedArea(''); // 区が変更されたらエリアをリセット
  };

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

  // 区選択によるエリアフィルター関数
  const filterByDistrict = (data: any[]) => {
    // 区が選択されていない場合はすべて表示
    if (!selectedDistrict) return data;
    
    // 選択された区のエリアリストを取得
    const districtAreas = areasByDistrict[selectedDistrict] || [];
    
    // データのエリアが選択された区に含まれているか確認
    return data.filter(d => {
      const areaName = d.area_name;
      // area_nameがnullまたはundefinedの場合（全体集計データ）は、
      // 区選択時は表示しない
      if (!areaName) return false;
      return districtAreas.includes(areaName);
    });
  };

  // 区選択時は個別取引データから価格推移を再計算
  const calculateDistrictTrends = () => {
    if (!selectedDistrict || !transactions.length) return priceTrends;
    
    const districtAreas = areasByDistrict[selectedDistrict] || [];
    const districtTransactions = transactions.filter(t => districtAreas.includes(t.area_name));
    
    // 期間ごとにグループ化して集計
    const trendMap = new Map<string, { sum: number; count: number; sumPrice: number }>();
    
    districtTransactions.forEach(t => {
      if (!t.price_per_sqm || !t.transaction_year || !t.transaction_quarter) return;
      
      const key = `${t.transaction_year}-${t.transaction_quarter}`;
      const existing = trendMap.get(key) || { sum: 0, count: 0, sumPrice: 0 };
      
      trendMap.set(key, {
        sum: existing.sum + t.price_per_sqm,
        count: existing.count + 1,
        sumPrice: existing.sumPrice + (t.transaction_price || 0)
      });
    });
    
    // MapをPriceTrendDataの配列に変換
    const trends: PriceTrendData[] = [];
    trendMap.forEach((value, key) => {
      const [year, quarter] = key.split('-').map(Number);
      trends.push({
        year,
        quarter,
        avg_price_per_sqm: value.sum / value.count / 10000, // 万円/㎡に変換
        transaction_count: value.count
      });
    });
    
    // 年・四半期順にソート
    return trends.sort((a, b) => {
      const aValue = a.year * 4 + a.quarter;
      const bValue = b.year * 4 + b.quarter;
      return aValue - bValue;
    });
  };
  
  // 区選択時は広さ別データも再計算
  const calculateDistrictSizeTrends = () => {
    if (!selectedDistrict || !transactions.length) return sizeTrends;
    
    const districtAreas = areasByDistrict[selectedDistrict] || [];
    const districtTransactions = transactions.filter(t => districtAreas.includes(t.area_name));
    
    // 広さカテゴリーの定義
    const sizeCategories = [
      { name: "20㎡未満", min: 0, max: 20 },
      { name: "20-40㎡", min: 20, max: 40 },
      { name: "40-60㎡", min: 40, max: 60 },
      { name: "60-80㎡", min: 60, max: 80 },
      { name: "80-100㎡", min: 80, max: 100 },
      { name: "100㎡以上", min: 100, max: 999 }
    ];
    
    const results: any[] = [];
    
    // カテゴリーごとに集計
    sizeCategories.forEach(category => {
      const categoryMap = new Map<string, { sum: number; count: number }>();
      
      districtTransactions.forEach(t => {
        if (!t.price_per_sqm || !t.floor_area || !t.transaction_year || !t.transaction_quarter) return;
        if (t.floor_area < category.min || t.floor_area >= category.max) return;
        
        const key = `${t.transaction_year}-${t.transaction_quarter}`;
        const existing = categoryMap.get(key) || { sum: 0, count: 0 };
        
        categoryMap.set(key, {
          sum: existing.sum + t.price_per_sqm,
          count: existing.count + 1
        });
      });
      
      categoryMap.forEach((value, key) => {
        const [year, quarter] = key.split('-').map(Number);
        results.push({
          category: category.name,
          year,
          quarter,
          avg_price_per_sqm: value.sum / value.count / 10000,
          transaction_count: value.count
        });
      });
    });
    
    return results;
  };
  
  // 区選択時は築年別データも再計算
  const calculateDistrictAgeTrends = () => {
    if (!selectedDistrict || !transactions.length) return ageTrends;
    
    const districtAreas = areasByDistrict[selectedDistrict] || [];
    const districtTransactions = transactions.filter(t => districtAreas.includes(t.area_name));
    
    // 築年カテゴリーの定義
    const ageCategories = [
      { name: "築5年以内", min: 0, max: 5 },
      { name: "築5-10年", min: 5, max: 10 },
      { name: "築10-15年", min: 10, max: 15 },
      { name: "築15-20年", min: 15, max: 20 },
      { name: "築20年超", min: 20, max: 100 }
    ];
    
    const results: any[] = [];
    
    // カテゴリーごとに集計
    ageCategories.forEach(category => {
      const categoryMap = new Map<string, { sum: number; count: number }>();
      
      districtTransactions.forEach(t => {
        if (!t.price_per_sqm || !t.built_year || !t.transaction_year || !t.transaction_quarter) return;
        
        const age = t.transaction_year - t.built_year;
        if (age < category.min || age >= category.max) return;
        
        const key = `${t.transaction_year}-${t.transaction_quarter}`;
        const existing = categoryMap.get(key) || { sum: 0, count: 0 };
        
        categoryMap.set(key, {
          sum: existing.sum + t.price_per_sqm,
          count: existing.count + 1
        });
      });
      
      categoryMap.forEach((value, key) => {
        const [year, quarter] = key.split('-').map(Number);
        results.push({
          category: category.name,
          year,
          quarter,
          avg_price_per_sqm: value.sum / value.count / 10000,
          transaction_count: value.count
        });
      });
    });
    
    return results;
  };
  
  // フィルタリング済みデータ（期間と区の両方でフィルター）
  const districtPriceTrends = selectedDistrict ? calculateDistrictTrends() : priceTrends;
  const districtSizeTrends = selectedDistrict ? calculateDistrictSizeTrends() : sizeTrends;
  const districtAgeTrends = selectedDistrict ? calculateDistrictAgeTrends() : ageTrends;
  
  const filteredPriceTrends = filterByPeriod(districtPriceTrends);
  const filteredTransactions = filterByDistrict(filterByPeriod(transactions));
  const filteredSizeTrends = filterByPeriod(districtSizeTrends);
  const filteredAgeTrends = filterByPeriod(districtAgeTrends);



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
          成約価格情報
        </Typography>

        {/* データ出典説明 */}
        <Paper sx={{ p: 2, mb: 3, bgcolor: 'info.main', color: 'info.contrastText' }}>
          <Typography variant="body2">
            本データは国土交通省のWEBサイト
            <a
              href="https://www.reinfolib.mlit.go.jp/"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: 'inherit', fontWeight: 'bold' }}
            >
              「不動産情報ライブラリ」
            </a>
            から取得した成約価格情報をもとに集計・分析したものです。
          </Typography>
          <Typography variant="caption" sx={{ mt: 1, display: 'block' }}>
            ※指定流通機構（レインズ）保有の不動産取引価格情報を、国土交通省が個別の不動産取引が特定できないよう加工し、
            消費者向け不動産取引情報サービス「レインズ・マーケット・インフォメーション」（RMI）にて公表している情報
          </Typography>
        </Paper>

        {/* フィルター */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            期間を選択してください（{startYear}年Q{startQuarter} ～ {endYear}年Q{endQuarter}）
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <FormControl fullWidth>
                <InputLabel>区を選択</InputLabel>
                <Select
                  value={selectedDistrict}
                  onChange={handleDistrictChange}
                  label="区を選択"
                >
                  <MenuItem value="">全区</MenuItem>
                  {Object.keys(areasByDistrict).map(district => (
                    <MenuItem key={district} value={district}>{district}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <FormControl fullWidth disabled={!selectedDistrict}>
                <InputLabel>エリアを選択</InputLabel>
                <Select
                  value={selectedArea}
                  onChange={handleAreaChange}
                  label="エリアを選択"
                >
                  <MenuItem value="">全エリア</MenuItem>
                  {selectedDistrict && areasByDistrict[selectedDistrict]?.map(area => (
                    <MenuItem key={area} value={area}>{area}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
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
            <Grid item xs={6} sm={2} md={1}>
              <FormControl fullWidth>
                <InputLabel>Q</InputLabel>
                <Select
                  value={startQuarter}
                  onChange={handleStartQuarterChange}
                  label="Q"
                >
                  {[1, 2, 3, 4]
                    .filter(q => startYear < endYear || q <= endQuarter)
                    .map(q => (
                      <MenuItem key={q} value={q}>Q{q}</MenuItem>
                    ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
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
            <Grid item xs={6} sm={2} md={1}>
              <FormControl fullWidth>
                <InputLabel>Q</InputLabel>
                <Select
                  value={endQuarter}
                  onChange={handleEndQuarterChange}
                  label="Q"
                >
                  {[1, 2, 3, 4]
                    .filter(q => startYear < endYear || q >= startQuarter)
                    .map(q => (
                      <MenuItem key={q} value={q}>Q{q}</MenuItem>
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
                    <table style={{
                      width: '100%',
                      borderCollapse: 'collapse',
                      fontSize: isMobile ? '0.85rem' : '0.9rem'
                    }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid #ddd', backgroundColor: '#f5f5f5' }}>
                          <th style={{
                            padding: isMobile ? '10px 12px' : '8px',
                            textAlign: 'left',
                            whiteSpace: 'nowrap',
                            width: isMobile ? '40%' : 'auto'
                          }}>
                            期間
                          </th>
                          <th style={{
                            padding: isMobile ? '10px 12px' : '8px',
                            textAlign: 'right',
                            whiteSpace: 'nowrap',
                            width: isMobile ? '25%' : 'auto'
                          }}>
                            {isMobile ? '件数' : '取引件数'}
                          </th>
                          <th style={{
                            padding: isMobile ? '10px 12px' : '8px',
                            textAlign: 'right',
                            whiteSpace: 'nowrap',
                            width: isMobile ? '35%' : 'auto'
                          }}>
                            {isMobile ? '単価' : '平均単価'}<br/>
                            <span style={{ fontSize: '0.8em' }}>{isMobile ? '(万/㎡)' : '（万円/㎡）'}</span>
                          </th>
                          {selectedArea && (
                            <th style={{
                              padding: isMobile ? '10px 12px' : '8px',
                              textAlign: 'right',
                              whiteSpace: 'nowrap'
                            }}>
                              エリア
                            </th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPriceTrends.map((trend, index) => (
                          <tr key={`${trend.year}-${trend.quarter}`} style={{
                            borderBottom: '1px solid #eee',
                            backgroundColor: index % 2 === 0 ? 'white' : '#fafafa'
                          }}>
                            <td style={{
                              padding: isMobile ? '10px 12px' : '8px',
                              fontSize: isMobile ? '0.85rem' : '0.9rem',
                              whiteSpace: 'nowrap'
                            }}>
                              {isMobile ?
                                `${trend.year}年Q${trend.quarter}` :
                                `${trend.year}年第${trend.quarter}四半期`
                              }
                            </td>
                            <td style={{
                              padding: isMobile ? '10px 12px' : '8px',
                              textAlign: 'right',
                              fontSize: isMobile ? '0.85rem' : '0.9rem',
                              fontWeight: 'bold'
                            }}>
                              {trend.transaction_count}
                            </td>
                            <td style={{
                              padding: isMobile ? '10px 12px' : '8px',
                              textAlign: 'right',
                              fontSize: isMobile ? '0.85rem' : '0.9rem',
                              fontWeight: 'bold',
                              color: '#1976d2'
                            }}>
                              {trend.avg_price_per_sqm.toFixed(1)}
                            </td>
                            {selectedArea && (
                              <td style={{
                                padding: isMobile ? '10px 12px' : '8px',
                                textAlign: 'right',
                                fontSize: isMobile ? '0.85rem' : '0.9rem',
                                whiteSpace: 'nowrap'
                              }}>
                                {trend.area_name || selectedArea}
                              </td>
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
                      個別取引一覧（{filteredTransactions.length.toLocaleString()}件）
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {startIndex + 1}～{Math.min(endIndex, filteredTransactions.length)}件を表示
                    </Typography>
                  </Stack>
                  
                  <Box sx={{ overflowX: 'auto' }}>
                    <table style={{
                      width: isMobile ? 'auto' : '100%',
                      borderCollapse: 'collapse',
                      fontSize: isMobile ? '0.85rem' : '0.9rem'
                    }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid #ddd', backgroundColor: '#f5f5f5' }}>
                          {!isMobile && <th style={{ padding: '8px', textAlign: 'center', minWidth: '30px' }}>No.</th>}
                          <th
                            style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'left',
                              minWidth: isMobile ? '50px' : '100px',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('transaction_year')}
                          >
                            {isMobile ? '時期' : '取引時期'}
                            {orderBy === 'transaction_year' && (
                              <span style={{ marginLeft: '2px', fontSize: '0.8em' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th
                            style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'left',
                              cursor: 'pointer',
                              userSelect: 'none',
                              whiteSpace: 'nowrap'
                            }}
                            onClick={() => handleRequestSort('area_name')}
                          >
                            エリア
                            {orderBy === 'area_name' && (
                              <span style={{ marginLeft: '2px', fontSize: '0.8em' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th
                            style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'right',
                              minWidth: isMobile ? '55px' : '100px',
                              cursor: 'pointer',
                              userSelect: 'none',
                              whiteSpace: 'nowrap'
                            }}
                            onClick={() => handleRequestSort('transaction_price')}
                          >
                            {isMobile ? '価格' : '取引価格'}<br/>
                            <span style={{ fontSize: '0.8em' }}>(万円)</span>
                            {orderBy === 'transaction_price' && (
                              <span style={{ marginLeft: '2px', fontSize: '0.8em' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th
                            style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'right',
                              minWidth: isMobile ? '40px' : '80px',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('price_per_sqm')}
                          >
                            {isMobile ? '㎡単' : '単価'}<br/>
                            <span style={{ fontSize: '0.8em' }}>(万)</span>
                            {orderBy === 'price_per_sqm' && (
                              <span style={{ marginLeft: '2px', fontSize: '0.8em' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th
                            style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'right',
                              minWidth: isMobile ? '35px' : '70px',
                              cursor: 'pointer',
                              userSelect: 'none'
                            }}
                            onClick={() => handleRequestSort('floor_area')}
                          >
                            面積<br/>
                            <span style={{ fontSize: '0.8em' }}>(㎡)</span>
                            {orderBy === 'floor_area' && (
                              <span style={{ marginLeft: '2px', fontSize: '0.8em' }}>
                                {order === 'desc' ? '▼' : '▲'}
                              </span>
                            )}
                          </th>
                          <th style={{
                            padding: isMobile ? '8px 10px' : '8px',
                            textAlign: 'left',
                            minWidth: isMobile ? '50px' : '60px',
                            whiteSpace: 'nowrap'
                          }}>
                            間取り
                          </th>
                          {!isMobile && <th style={{ padding: '8px', textAlign: 'left' }}>建築年</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {paginatedTransactions.map((transaction, index) => (
                          <tr key={transaction.id} style={{
                            borderBottom: '1px solid #eee',
                            backgroundColor: index % 2 === 0 ? 'white' : '#fafafa'
                          }}>
                            {!isMobile && (
                              <td style={{ padding: '8px', textAlign: 'center', fontSize: '0.85rem' }}>
                                {startIndex + index + 1}
                              </td>
                            )}
                            <td style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              fontSize: isMobile ? '0.8rem' : '0.9rem',
                              whiteSpace: 'nowrap'
                            }}>
                              {isMobile ?
                                `${String(transaction.transaction_year).slice(-2)}Q${transaction.transaction_quarter}` :
                                `${transaction.transaction_year}年Q${transaction.transaction_quarter}`
                              }
                            </td>
                            <td style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              fontSize: isMobile ? '0.8rem' : '0.9rem',
                              whiteSpace: 'nowrap'
                            }}>{transaction.area_name}</td>
                            <td style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'right',
                              fontSize: isMobile ? '0.8rem' : '0.9rem',
                              whiteSpace: 'nowrap',
                              fontWeight: isMobile ? 'bold' : 'normal'
                            }}>
                              {transaction.transaction_price?.toLocaleString() || '-'}
                            </td>
                            <td style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'right',
                              fontSize: isMobile ? '0.8rem' : '0.9rem',
                              whiteSpace: 'nowrap'
                            }}>
                              {transaction.price_per_sqm ?
                                (transaction.price_per_sqm / 10000).toFixed(1) : '-'}
                            </td>
                            <td style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              textAlign: 'right',
                              fontSize: isMobile ? '0.8rem' : '0.9rem',
                              whiteSpace: 'nowrap'
                            }}>
                              {transaction.floor_area?.toFixed(1) || '-'}
                            </td>
                            <td style={{
                              padding: isMobile ? '8px 10px' : '8px',
                              fontSize: isMobile ? '0.8rem' : '0.9rem',
                              whiteSpace: 'nowrap'
                            }}>
                              {(() => {
                                let layout = transaction.layout || '-';
                                if (layout !== '-') {
                                  // 全角英数字を半角に変換
                                  layout = layout
                                    .replace(/[０-９]/g, s => String.fromCharCode(s.charCodeAt(0) - 0xFEE0))
                                    .replace(/[Ａ-Ｚａ-ｚ]/g, s => String.fromCharCode(s.charCodeAt(0) - 0xFEE0))
                                    .replace(/　/g, ' ')
                                    .replace(/（/g, '(')
                                    .replace(/）/g, ')');
                                }
                                return layout;
                              })()}
                            </td>
                            {!isMobile && (
                              <td style={{ padding: '8px' }}>{transaction.built_year ? `${transaction.built_year}年` : '-'}</td>
                            )}
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