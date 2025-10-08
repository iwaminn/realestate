import React, { useState, useEffect } from 'react';
import { Helmet } from 'react-helmet-async';
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
  Button,
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
  area_name?: string;
}

type OrderBy = 'transaction_year' | 'area_name' | 'transaction_price' | 'price_per_sqm' | 'floor_area';
type Order = 'asc' | 'desc';

const TransactionPricesPage: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [statsLoading, setStatsLoading] = useState(false);
  const [transactionsLoading, setTransactionsLoading] = useState(false);
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
  const [top5DistrictTrends, setTop5DistrictTrends] = useState<{[key: string]: PriceTrendData[]}>({});
  const [transactions, setTransactions] = useState<TransactionData[]>([]);
  const [sizeTrends, setSizeTrends] = useState<any[]>([]);
  const [ageTrends, setAgeTrends] = useState<any[]>([]);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [rowsPerPage] = useState<number>(50);
  const [orderBy, setOrderBy] = useState<OrderBy>('transaction_year');
  const [order, setOrder] = useState<Order>('desc');
  const [totalTransactions, setTotalTransactions] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(0);

  // 並び替えハンドラー
  const handleRequestSort = (property: OrderBy) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
    setCurrentPage(1); // 並び替え時はページを1に戻す
  };

  // ページ変更ハンドラー
  const handlePageChange = (event: React.ChangeEvent<unknown>, value: number) => {
    setCurrentPage(value);
  };

  // エリア一覧を取得
  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const [areasRes, areasByDistrictRes] = await Promise.all([
          axios.get('/transaction-prices/areas'),
          axios.get('/transaction-prices/areas-by-district')
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
      setStatsLoading(true);
      try {
        // 共通パラメータ（期間フィルター）
        const periodParams: any = {
          start_year: startYear,
          start_quarter: startQuarter,
          end_year: endYear,
          end_quarter: endQuarter
        };

        // エリア統計用パラメータ
        const statsParams: any = { ...periodParams };

        // グラフ用のパラメータ
        const trendParams: any = { ...periodParams };
        if (selectedArea) {
          trendParams.area = selectedArea;
        } else if (selectedDistrict) {
          trendParams.district = selectedDistrict;
        }

        // 広さ別・築年別用パラメータ
        const sizeTrendsParams: any = { ...periodParams };
        const ageTrendsParams: any = { ...periodParams };
        if (selectedDistrict && !selectedArea) {
          sizeTrendsParams.district = selectedDistrict;
          ageTrendsParams.district = selectedDistrict;
        }

        const [statsRes, trendsRes, sizeTrendsRes, ageTrendsRes] = await Promise.all([
          axios.get('/transaction-prices/statistics/by-area', { params: statsParams }),
          axios.get('/transaction-prices/trends', { params: trendParams }),
          axios.get('/transaction-prices/trends-by-size', { params: sizeTrendsParams }),
          axios.get('/transaction-prices/trends-by-age', { params: ageTrendsParams })
        ]);

        setAreaStats(statsRes.data);
        setPriceTrends(trendsRes.data);
        setSizeTrends(sizeTrendsRes.data);
        setAgeTrends(ageTrendsRes.data);

        // 区で絞り込んでいない場合、都心5区の推移データを取得
        if (!selectedDistrict && !selectedArea) {
          const top5Districts = ['千代田区', '中央区', '港区', '新宿区', '渋谷区'];
          const districtPromises = top5Districts.map((district: string) =>
            axios.get('/transaction-prices/trends', {
              params: { district, ...periodParams }
            })
          );

          const districtResults = await Promise.all(districtPromises);
          const trendsMap: {[key: string]: PriceTrendData[]} = {};

          top5Districts.forEach((district: string, index: number) => {
            trendsMap[district] = districtResults[index].data;
          });

          setTop5DistrictTrends(trendsMap);
        } else {
          setTop5DistrictTrends({});
        }

        // 上位5エリアの時系列データを取得（区選択時のみ）
        if (statsRes.data.length > 0 && !selectedArea && selectedDistrict) {
          const topAreaNames = statsRes.data.slice(0, 5).map((s: AreaStatistics) => s.area_name);
          const areaPromises = topAreaNames.map((area: string) =>
            axios.get('/transaction-prices/trends', { params: { area, ...periodParams } })
          );

          const areaResults = await Promise.all(areaPromises);
          const trendsMap: {[key: string]: PriceTrendData[]} = {};

          topAreaNames.forEach((area: string, index: number) => {
            trendsMap[area] = areaResults[index].data;
          });

          setAreaSpecificTrends(trendsMap);
        } else {
          setAreaSpecificTrends({});
        }
      } catch (error) {
        console.error('データ取得エラー:', error);
      } finally {
        setStatsLoading(false);
      }
    };
    fetchData();
  }, [selectedArea, selectedDistrict, startYear, startQuarter, endYear, endQuarter]);

  // 個別取引データを取得（ページネーション対応）
  useEffect(() => {
    const fetchTransactions = async () => {
      setTransactionsLoading(true);
      try {
        const params: any = {
          page: currentPage,
          page_size: rowsPerPage,
          order_by: orderBy,
          order: order
        };

        // フィルターパラメータ
        if (selectedArea) params.area = selectedArea;
        if (selectedDistrict && !selectedArea) params.district = selectedDistrict;
        if (selectedYear) params.year = selectedYear;
        if (startYear) params.start_year = startYear;
        if (startQuarter) params.start_quarter = startQuarter;
        if (endYear) params.end_year = endYear;
        if (endQuarter) params.end_quarter = endQuarter;

        const response = await axios.get('/transaction-prices/transactions', { params });

        setTransactions(response.data.data || []);
        setTotalTransactions(response.data.total || 0);
        setTotalPages(response.data.total_pages || 0);
      } catch (error) {
        console.error('取引データ取得エラー:', error);
        setTransactions([]);
        setTotalTransactions(0);
        setTotalPages(0);
      } finally {
        setTransactionsLoading(false);
      }
    };

    fetchTransactions();
  }, [selectedArea, selectedDistrict, selectedYear, startYear, startQuarter, endYear, endQuarter, currentPage, rowsPerPage, orderBy, order]);

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

  // バックエンドで期間フィルタリング済みのため、フロントエンドでの追加フィルタリングは不要



  // 表示用のインデックス計算
  const startIndex = (currentPage - 1) * rowsPerPage;
  const endIndex = Math.min(startIndex + rowsPerPage, totalTransactions);



  // フィルター変更時にページをリセット
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedArea, startYear, startQuarter, endYear, endQuarter]);

  // グラフ共通のレスポンシブオプション
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: isMobile ? 1.2 : 2,
    plugins: {
      legend: {
        display: true,
        position: 'top' as const,
        labels: {
          boxWidth: isMobile ? 12 : 20,
          font: {
            size: isMobile ? 10 : 12
          }
        }
      },
      tooltip: {
        enabled: true,
        mode: 'index' as const,
        intersect: false,
      }
    },
    scales: {
      x: {
        ticks: {
          font: {
            size: isMobile ? 9 : 11
          },
          maxRotation: isMobile ? 45 : 0,
          minRotation: isMobile ? 45 : 0
        }
      },
      y: {
        ticks: {
          font: {
            size: isMobile ? 9 : 11
          }
        }
      }
    }
  };

  // 価格推移チャートのデータ
  const trendChartData = {
    labels: priceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: [
      {
        label: selectedArea ? selectedArea : selectedDistrict ? `${selectedDistrict}平均` : '全体平均',
        data: priceTrends.map(d => d.avg_price_per_sqm),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.5)',
        borderWidth: 3,
        tension: 0.1,
      },
      // 都心5区の推移（区で絞り込んでいない場合のみ表示）
      ...(!selectedDistrict && !selectedArea && Object.keys(top5DistrictTrends).length > 0
        ? Object.entries(top5DistrictTrends).map(([district, trends], index) => {
            const colors = [
              'rgba(255, 99, 132, 1)',    // 千代田区 - 赤
              'rgba(54, 162, 235, 1)',    // 中央区 - 青
              'rgba(255, 206, 86, 1)',    // 港区 - 黄
              'rgba(153, 102, 255, 1)',   // 新宿区 - 紫
              'rgba(255, 159, 64, 1)',    // 渋谷区 - オレンジ
            ];

            const dataMap = new Map(
              trends.map(t => [`${t.year}Q${t.quarter}`, t.avg_price_per_sqm])
            );

            return {
              label: district,
              data: priceTrends.map(d => {
                const key = `${d.year}Q${d.quarter}`;
                return dataMap.get(key) || null;
              }),
              borderColor: colors[index % colors.length],
              backgroundColor: colors[index % colors.length].replace('1)', '0.2)'),
              borderWidth: 2,
              borderDash: [5, 5],  // 点線
              tension: 0.1,
            };
          })
        : [])
    ]
  };

  // 取引件数推移チャートのデータ
  const volumeChartData = {
    labels: priceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: [
      {
        label: '取引件数',
        data: priceTrends.map(d => d.transaction_count),
        backgroundColor: 'rgba(54, 162, 235, 0.5)',
        borderColor: 'rgba(54, 162, 235, 1)',
        borderWidth: 1,
      }
    ]
  };



  // 広さ別価格推移チャート
  const sizeCategories = [...new Set(sizeTrends.map(d => d.category))];
  const sizeTrendChartData = {
    labels: priceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: sizeCategories.map((category, index) => {
      const colors = [
        'rgba(255, 99, 132, 1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
        'rgba(255, 159, 64, 1)',
      ];

      const categoryTrends = sizeTrends.filter(d => d.category === category);
      const dataMap = new Map(
        categoryTrends.map(t => [`${t.year}Q${t.quarter}`, t.avg_price_per_sqm])
      );

      return {
        label: category,
        data: priceTrends.map(d => {
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
  const ageCategories = [...new Set(ageTrends.map(d => d.category))];
  const ageTrendChartData = {
    labels: priceTrends.map(d => `${d.year}年Q${d.quarter}`),
    datasets: ageCategories.map((category, index) => {
      const colors = [
        'rgba(255, 99, 132, 1)',
        'rgba(54, 162, 235, 1)',
        'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)',
        'rgba(153, 102, 255, 1)',
      ];

      const categoryTrends = ageTrends.filter(d => d.category === category);
      const dataMap = new Map(
        categoryTrends.map(t => [`${t.year}Q${t.quarter}`, t.avg_price_per_sqm])
      );

      return {
        label: category,
        data: priceTrends.map(d => {
          const key = `${d.year}Q${d.quarter}`;
          return dataMap.get(key) || null;
        }),
        borderColor: colors[index % colors.length],
        backgroundColor: colors[index % colors.length].replace('1)', '0.2)'),
        tension: 0.1,
      };
    })
  };

  // SEO用のタイトルと説明文を生成
  const generatePageTitle = () => {
    const parts: string[] = [];

    if (selectedArea) {
      parts.push(selectedArea);
    } else if (selectedDistrict) {
      parts.push(selectedDistrict);
    }

    if (selectedYear) {
      parts.push(`${selectedYear}年`);
    }

    const condition = parts.length > 0 ? `${parts.join(' ')}の` : '';
    return `${condition}マンション成約価格情報 | 都心マンション価格チェッカー`;
  };

  const generatePageDescription = () => {
    const parts: string[] = [];

    if (selectedArea) {
      parts.push(selectedArea);
    } else if (selectedDistrict) {
      parts.push(selectedDistrict);
    }

    if (selectedYear) {
      parts.push(`${selectedYear}年`);
    }

    const condition = parts.length > 0 ? `${parts.join(' ')}の` : '';
    return `${condition}中古マンション成約価格情報。国土交通省のデータに基づく実際の取引価格や価格推移を確認できます。`;
  };

  const pageTitle = generatePageTitle();
  const pageDescription = generatePageDescription();

  return (
    <>
      <Helmet>
        <title>{pageTitle}</title>
        <meta name="description" content={pageDescription} />
      </Helmet>
      <Container maxWidth="lg" sx={{ px: isMobile ? 0.5 : 3 }}>
      <Box sx={{ py: isMobile ? 1 : 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ mb: isMobile ? 1 : 2 }}>
          成約価格情報
        </Typography>

        {/* データ出典説明 */}
        <Paper sx={{ p: isMobile ? 1.5 : 2, mb: isMobile ? 1.5 : 3, bgcolor: 'info.main', color: 'info.contrastText' }}>
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
        <Paper sx={{ p: isMobile ? 1.5 : 2, mb: isMobile ? 1.5 : 3 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            期間を選択してください（{startYear}年Q{startQuarter} ～ {endYear}年Q{endQuarter}）
          </Typography>
          <Grid container spacing={isMobile ? 1.5 : 2}>
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

        <>
          {/* グラフ・統計情報エリア */}
          <Box sx={{ position: 'relative', minHeight: statsLoading ? '400px' : 'auto' }}>
            {statsLoading && (
              <Box
                display="flex"
                justifyContent="center"
                alignItems="center"
                sx={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  bgcolor: 'rgba(255, 255, 255, 0.7)',
                  zIndex: 1
                }}
              >
                <CircularProgress />
              </Box>
            )}

            {/* 価格推移チャート */}
            {priceTrends.length > 0 && (
              <Card sx={{ mb: isMobile ? 1.5 : 3 }}>
                <CardContent sx={{ p: isMobile ? 1.5 : 2, '&:last-child': { pb: isMobile ? 1.5 : 2 } }}>
                  <Typography variant="h6" gutterBottom>
                    価格推移
                    {selectedArea && <Chip label={selectedArea} sx={{ ml: 2 }} />}
                    <Chip label={`${startYear}年Q${startQuarter} ～ ${endYear}年Q${endQuarter}`} sx={{ ml: 1 }} size="small" />
                  </Typography>
                  <Line data={trendChartData} options={chartOptions} />
                </CardContent>
              </Card>
            )}

            {/* 取引件数推移チャート */}
            {priceTrends.length > 0 && (
              <Card sx={{ mb: isMobile ? 1.5 : 3 }}>
                <CardContent sx={{ p: isMobile ? 1.5 : 2, '&:last-child': { pb: isMobile ? 1.5 : 2 } }}>
                  <Typography variant="h6" gutterBottom>
                    取引件数推移
                    {selectedArea && <Chip label={selectedArea} sx={{ ml: 2 }} />}
                    <Chip label={`${startYear}年Q${startQuarter} ～ ${endYear}年Q${endQuarter}`} sx={{ ml: 1 }} size="small" />
                  </Typography>
                  <Bar data={volumeChartData} options={chartOptions} />
                </CardContent>
              </Card>
            )}



            {/* 広さ別価格推移 */}
            {sizeTrends.length > 0 && (
              <Card sx={{ mb: isMobile ? 1.5 : 3 }}>
                <CardContent sx={{ p: isMobile ? 1.5 : 2, '&:last-child': { pb: isMobile ? 1.5 : 2 } }}>
                  <Typography variant="h6" gutterBottom>
                    広さ別単価推移
                  </Typography>
                  <Line data={sizeTrendChartData} options={chartOptions} />
                </CardContent>
              </Card>
            )}

            {/* 築年別価格推移 */}
            {ageTrends.length > 0 && (
              <Card sx={{ mb: isMobile ? 1.5 : 3 }}>
                <CardContent sx={{ p: isMobile ? 1.5 : 2, '&:last-child': { pb: isMobile ? 1.5 : 2 } }}>
                  <Typography variant="h6" gutterBottom>
                    築年別単価推移
                  </Typography>
                  <Line data={ageTrendChartData} options={chartOptions} />
                </CardContent>
              </Card>
            )}



            {/* 期間別統計テーブル */}
            {priceTrends.length > 0 && (
              <Card sx={{ mb: isMobile ? 1.5 : 3 }}>
                <CardContent sx={{ p: isMobile ? 1.5 : 2, '&:last-child': { pb: isMobile ? 1.5 : 2 } }}>
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
                        {priceTrends.map((trend, index) => (
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

          </Box>

          {/* 個別取引一覧エリア */}
          <Box sx={{ position: 'relative', minHeight: transactionsLoading ? '400px' : 'auto' }}>
            {transactionsLoading && (
              <Box
                display="flex"
                justifyContent="center"
                alignItems="center"
                sx={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  bgcolor: 'rgba(255, 255, 255, 0.7)',
                  zIndex: 1
                }}
              >
                <CircularProgress />
              </Box>
            )}

            {/* 個別取引一覧 */}
            {transactions.length > 0 && (
              <Card>
                <CardContent sx={{ p: isMobile ? 1.5 : 2, '&:last-child': { pb: isMobile ? 1.5 : 2 } }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                    <Typography variant="h6">
                      個別取引一覧（全{totalTransactions.toLocaleString()}件）
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {startIndex + 1}～{endIndex}件を表示
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
                        {transactions.map((transaction, index) => (
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
                                    .replace(/[０-９]/g, (s: string) => String.fromCharCode(s.charCodeAt(0) - 0xFEE0))
                                    .replace(/[Ａ-Ｚａ-ｚ]/g, (s: string) => String.fromCharCode(s.charCodeAt(0) - 0xFEE0))
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
                        onChange={handlePageChange}
                        color="primary"
                        showFirstButton
                        showLastButton
                      />
                    </Box>
                  )}


                </CardContent>
              </Card>
            )}
          </Box>
        </>
      </Box>
    </Container>
    </>
  );
};

export default TransactionPricesPage;