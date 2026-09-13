// react packages
import { useState, useEffect, useLayoutEffect, useRef } from "react";
import CloseIcon from '@mui/icons-material/Close';

// mui packages
import Button from '@mui/material/Button';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Divider from '@mui/material/Divider';
import Slider from '@mui/material/Slider';
import Box from '@mui/material/Box';
import GradientCircularProgress from '../Components/GradientCircularProgress';

// SVG package

import { getDataList, getCoord, getFilteredLayout } from '../services/API';

// style
import { KELLYCOLORS } from '../Config'

export default function OCDFGLayout() {
    var animationSeconds = '0s'
    const [data, setData] = useState([]);
    const [dataSelected, setDataSelected] = useState("");
    const [processLayout, setProcessLayout] = useState("");
    const [objectTypes, setObjectTypes] = useState([]);
    const [loaderOn, setLoaderOn] = useState(false);
    const [filterValue, setFilterValue] = useState(100);           // % of edges kept (100 = all)
    const [zoom, setZoom] = useState(100);                         // drawing width in % of the panel
    const [edgeInfo, setEdgeInfo] = useState(null);                // {lines, x, y}: info box of the clicked edge
    const ZOOM_MIN = 10, ZOOM_MAX = 200;
    const fitZoom = useRef(100);                // zoom at which the whole drawing is visible
    const drawingRef = useRef(null);            // the zoomable wrapper around the SVG
    const zoomAnchor = useRef(null);            // {x, y, prevZoom}: keep this point fixed while zooming

    const clampZoom = (z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(z)));

    // Zoom so that the whole drawing fits both the width and the visible height of the panel
    const computeFitZoom = () => {
        const wrapper = drawingRef.current;
        const svg = wrapper && wrapper.querySelector('svg[viewBox]');
        const scroller = wrapper && wrapper.closest('.process-model-visualization');
        if (!svg || !scroller) return 100;
        const [, , vbW, vbH] = svg.getAttribute('viewBox').split(' ').map(Number);
        const fullWidth = wrapper.parentElement.clientWidth;             // width at zoom 100
        // top of the drawing in the window when nothing is scrolled
        const top = wrapper.getBoundingClientRect().top + scroller.scrollTop + window.scrollY;
        const availableHeight = window.innerHeight - top - 20;
        const heightAt100 = fullWidth * vbH / vbW;
        return clampZoom(Math.min(100, 100 * availableHeight / heightAt100));
    };

    // After Visualize, start at the zoom that shows the whole drawing; filters keep the current zoom
    const refitOnNextDraw = useRef(false);
    useLayoutEffect(() => {
        if (!processLayout) return;
        fitZoom.current = computeFitZoom();
        if (refitOnNextDraw.current) {
            refitOnNextDraw.current = false;
            setZoom(fitZoom.current);
        }
    }, [processLayout]);

    // Zoom by `factor` keeping the page point (clientX, clientY) under the cursor
    // Change the zoom so that the drawing point currently under (clientX, clientY) stays there
    const zoomTo = (next, clientX, clientY) => {
        const wrapper = drawingRef.current;
        if (!wrapper) return;
        setZoom(prev => {
            next = clampZoom(typeof next === 'function' ? next(prev) : next);
            if (next === prev) return prev;
            const rect = wrapper.getBoundingClientRect();
            // fraction of the drawing under the anchor + where it is on screen
            zoomAnchor.current = { fx: (clientX - rect.left) / rect.width, fy: (clientY - rect.top) / rect.height,
                                   clientX, clientY };
            return next;
        });
    };

    const zoomAt = (factor, clientX, clientY) => zoomTo(prev => prev * factor, clientX, clientY);

    // Zoom keeping the centre of the visible area in place (buttons, slider, Fit)
    const zoomKeepingCenter = (next) => {
        const scroller = drawingRef.current && drawingRef.current.closest('.process-model-visualization');
        if (!scroller) { setZoom(next); return; }
        const r = scroller.getBoundingClientRect();
        const area = drawingRef.current.parentElement.getBoundingClientRect();   // drawing area (without the filter-bar margin)
        zoomTo(next, area.left + area.width / 2, r.top + r.height / 2);
    };

    // Ctrl/⌘ + wheel over the drawing zooms; plain wheel keeps scrolling the page
    useEffect(() => {
        const wrapper = drawingRef.current;
        if (!wrapper) return;
        const onWheel = (e) => {
            if (!(e.ctrlKey || e.metaKey)) return;
            e.preventDefault();
            zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
        };
        wrapper.addEventListener('wheel', onWheel, { passive: false });
        return () => wrapper.removeEventListener('wheel', onWheel);
    }, [processLayout]);

    // Fit: zoom so the whole drawing is visible and scroll it into view
    const scrollToDrawing = useRef(false);
    const resetScroll = () => {
        const wrapper = drawingRef.current;
        if (!wrapper) return;
        wrapper.parentElement.scrollLeft = 0;
        const scroller = wrapper.closest('.process-model-visualization');
        if (scroller) scroller.scrollTop = 0;
    };
    const fitView = () => {
        zoomAnchor.current = null;
        if (zoom === fitZoom.current) { resetScroll(); return; }   // zoom unchanged: no re-render to wait for
        scrollToDrawing.current = true;
        setZoom(fitZoom.current);
    };

    // After the zoom is applied, scroll so the anchored drawing point is back where it was
    useLayoutEffect(() => {
        const wrapper = drawingRef.current;
        if (scrollToDrawing.current && wrapper) {
            scrollToDrawing.current = false;
            resetScroll();
        }
        const anchor = zoomAnchor.current;
        if (!anchor || !wrapper) return;
        zoomAnchor.current = null;
        const scroller = wrapper.closest('.process-model-visualization');
        if (!scroller) return;
        const rect = wrapper.getBoundingClientRect();   // already re-laid out at the new width
        wrapper.parentElement.scrollLeft += (rect.left + anchor.fx * rect.width) - anchor.clientX;   // drawing area scrolls horizontally
        scroller.scrollTop += (rect.top + anchor.fy * rect.height) - anchor.clientY;                 // page scrolls vertically
    }, [zoom]);
    var [oldNewData, setOldNewData] = useState([null, null]);
    const [selectedTypes, setSelectedTypes] = useState([]);   // selectedTypes[i]: objectTypes[i] shown?

    const [layoutObject, setLayoutObject] = useState(null); // 여기 추가!

    const [originalOutput, setOriginalOutput] = useState(null);


    useEffect(() => {
        getDataList().then(res => {
            setData(res['files']);
        })
    }, [])

    useEffect(() => {
        if (oldNewData[1] != null) {
            visualizeOCELProcess()
        }
    }, [oldNewData])

    useEffect(() => {
        document.querySelectorAll("animate").forEach((element) => {
            element.beginElement();
        });
    }, [processLayout])

    const handleChange = (event) => {
        setDataSelected(event.target.value);
    };

    const toggleObjectType = (e, index) => {
        let tempArr = [...selectedTypes];
        tempArr[index] = e.target.checked;
        setSelectedTypes(tempArr);
    };

    const getSelectedObjectTypes = () => objectTypes.filter((_, i) => selectedTypes[i]);

    // Apply the object-type selection and the frequency slider on the cached layout
    const applyFilters = async () => {
        if (!layoutObject || !originalOutput) return;
        const selected = getSelectedObjectTypes();
        if (selected.length === 0) { window.alert('Select at least one object type.'); return; }

        setLoaderOn(true);
        try {
            const res = await getFilteredLayout(layoutObject.pickle_path, selected, filterValue);
            showFilteredOutput(res.output);
        } catch (err) {
            window.alert('Filtering failed: ' + (err.response?.data?.detail || err.message));
        } finally {
            setLoaderOn(false);
        }
    };

    const showFilteredOutput = (filteredOutput) => {
        setOldNewData([oldNewData[1], filteredOutput]);   // animate from the layout currently on screen
        setLayoutObject({ ...layoutObject, output: filteredOutput });
    };

    const removeLoader = () => {
        setLoaderOn(false);
    };

    // 0 (rarest edge) .. 1 (most frequent edge) on a log scale, since frequencies are heavy-tailed
    const edgeWeight = (maxFreq, minFreq, freq) => {
        if (!(maxFreq > minFreq) || !(freq > 0)) return 1;
        const t = Math.log(freq / minFreq) / Math.log(maxFreq / minFreq);
        return Math.min(1, Math.max(0, t));
    };

    const getEdgeWidth = (maxFreq, minFreq, freq, k = 1) => {
        const MAXWIDTH = 30 * k, MINWIDTH = 3 * k;
        return MINWIDTH + (MAXWIDTH - MINWIDTH) * edgeWeight(maxFreq, minFreq, freq);
    };

    const getEdgeOpacity = (maxFreq, minFreq, freq) => 0.55 + 0.45 * edgeWeight(maxFreq, minFreq, freq);

    // --- Fetch initial layout ---
    const getCoordination = () => {
        const data_dir = data[dataSelected];

        if (!data_dir) {
            window.alert('Please Check the Target Data!');
        } else {
            setLoaderOn(true);
            getCoord(data_dir)
                .then(res => {
                    const output = res.output;
                    setOriginalOutput(res.output);        // 최초 output 저장
                    refitOnNextDraw.current = true;
                    setOldNewData([null, output]);
                    setObjectTypes(output.object_axis_order);
                    setSelectedTypes(output.object_axis_order.map(() => true));
                    setFilterValue(100);
                    setEdgeInfo(null);

                    // pickle_path를 layoutObject처럼 저장
                    setLayoutObject({ pickle_path: res.pickle_path, output: res.output });

                    setLoaderOn(false);
                }).catch(err => {
                    setLoaderOn(false);
                });
        }
    };

    // Get color method
    const getObjectColor = idx => {
        return "#" + KELLYCOLORS[idx]
    }

    // SVG path through `points` ([x, y] pairs) with the corners rounded by radius `r`;
    // the last segment is shortened by `trim` so an arrowhead can sit in front of the stroke
    const roundedPath = (points, r, trimEnd = 0, trimStart = 0) => {
        if (points.length < 2) return '';
        points = points.map(p => [...p]);
        const shorten = (end, prev, trim) => {          // pull `end` towards `prev` by `trim`
            const len = Math.hypot(end[0] - prev[0], end[1] - prev[1]);
            if (len === 0) return;
            const t = Math.min(trim, len * 0.45);
            end[0] -= (end[0] - prev[0]) / len * t;
            end[1] -= (end[1] - prev[1]) / len * t;
        };
        if (trimEnd > 0) shorten(points[points.length - 1], points[points.length - 2], trimEnd);
        if (trimStart > 0) shorten(points[0], points[1], trimStart);
        let d = `M ${points[0][0]} ${points[0][1]}`;
        for (let i = 1; i < points.length - 1; i++) {
            const [px, py] = points[i - 1], [cx, cy] = points[i], [nx, ny] = points[i + 1];
            const inLen = Math.hypot(cx - px, cy - py), outLen = Math.hypot(nx - cx, ny - cy);
            // always emit the same command sequence (L .. Q ..) so paths of the same edge
            // before/after a filter can be animated into each other
            const rr = Math.min(r, inLen / 2, outLen / 2);
            const ax = inLen ? cx - (cx - px) / inLen * rr : cx, ay = inLen ? cy - (cy - py) / inLen * rr : cy;   // corner entry
            const bx = outLen ? cx + (nx - cx) / outLen * rr : cx, by = outLen ? cy + (ny - cy) / outLen * rr : cy; // corner exit
            d += ` L ${ax} ${ay} Q ${cx} ${cy} ${bx} ${by}`;
        }
        const [lx, ly] = points[points.length - 1];
        return d + ` L ${lx} ${ly}`;
    };

    const visualizeOCELProcess = (drawAct=true) => {
        const animationSeconds = '0.5s'

        const data = oldNewData[1];
        const prevData = oldNewData[0];

        const nodes = data.nodes
        const edges = data.edges

        const maxFreq = data.maxFreq;
        const minFreq = data.minFreq;

        let nodeList = [];
        let nodeNameList = [];
        let edgeList = [];

        const R = data.radius || 20;            // sub-circle radius from the backend
        const ARROW_LEN = 2.5 * R;              // arrowhead length (user units)
        const k = R / 20;                       // drawing constants below were tuned for R = 20

        var prevNodes = null;

        if (prevData) {
            prevNodes = prevData.nodes
        }

        Object.keys(nodes).map((key1, index) => {
            const node = nodes[key1];
            // Real 노드인 경우만 드로잉
            if (node.is_real) {
                if (drawAct) {
                    // Node 이름
                    var addon = node.object_types.length - node.object_types.indexOf(node.object_axis)
                    nodeNameList.push(
                        <g>
                            <switch>
                            <foreignObject
                            x={node.x + 2 * R * addon}
                            y={node.y - 2 * R}
                            width={320 * k}
                            height={200 * k}
                            font-size={`${2.2 * k}em`}
                            font-weight="bold">
                            <p xmlns="http://www.w3.org/1999/xhtml">{node.name.replace('_', ' ')}</p>
                            </foreignObject>

                            </switch>
                        </g>
                            )
                }

                if (node.is_start == true || node.is_end == true) {
                    Object.keys(node.nodes_visualized).map((key2, index) => {
                        const subNode = node.nodes_visualized[key2]
                        if (prevData == null) {
                            nodeList.push(<ellipse
                                cx={subNode.x}
                                cy={subNode.y}
                                rx={R}
                                ry={R}
                                stroke={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                stroke-width={5 * k}
                                fill={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                id={node.name}
                                rank={node.rank}
                                order={node.order}
                                is_backbone={node.is_backbone}
                                />)
                        } else {
                            const prevNode = prevNodes[key1];
                            var prevSubNode = null
                            try { prevSubNode = prevNode.nodes_visualized[key2] }
                            catch (err) { prevSubNode = null }
                            if (prevSubNode) {
                                nodeList.push(<ellipse
                                    cx={prevSubNode.x}
                                    cy={subNode.y}
                                    rx={R}
                                    ry={R}
                                    stroke={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                    stroke-width={5 * k}
                                    fill={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                    id={node.name}
                                    rank={node.rank}
                                    order={node.order}
                                    is_backbone={node.is_backbone}
                                    >
                                        <animate attributeName="cx"
                                            dur={animationSeconds}  // animationSeconds 인자로 받음
                                            from={prevSubNode.x}
                                            to={subNode.x}
                                            fill="freeze"
                                        />
                                    </ellipse>)
                            } else {
                                nodeList.push(<ellipse
                                cx={subNode.x}
                                cy={subNode.y}
                                rx={R}
                                ry={R}
                                stroke={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                stroke-width={5 * k}
                                fill={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                id={node.name}
                                rank={node.rank}
                                order={node.order}
                                is_backbone={node.is_backbone}
                                />)
                            }
                        }
                    })
                } else {
                    Object.keys(node.nodes_visualized).map((key2, index) => {
                        const subNode = node.nodes_visualized[key2];
                        if (prevData == null) {
                            nodeList.push(<circle
                                cx={subNode.x}
                                cy={subNode.y}
                                r={subNode.r}
                                stroke={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                stroke-width={5 * k}
                                fill="white"
                                id={node.name}
                                rank={node.rank}
                                order={node.order}
                                is_backbone={node.is_backbone}
                                ></circle>)
                        } else {
                            const prevNode = prevNodes[key1];
                            var prevSubNode = null
                            try { prevSubNode = prevNode.nodes_visualized[key2] }
                            catch (err) { prevSubNode = null }
                            if (prevSubNode) {
                                nodeList.push(<circle
                                    cx={prevSubNode.x}
                                    cy={prevSubNode.y}
                                    r={subNode.r}
                                    stroke={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                    stroke-width={5 * k}
                                    fill="white"
                                    id={node.name}
                                    rank={node.rank}
                                    order={node.order}
                                    is_backbone={node.is_backbone}
                                    >
                                        <animate attributeName="cx"
                                        dur={animationSeconds}
                                        from={prevSubNode.x}
                                        to={subNode.x}
                                        fill="freeze"
                                        />
                                    </circle>)
                            } else {
                                nodeList.push(<circle
                                    cx={subNode.x}
                                    cy={subNode.y}
                                    r={subNode.r}
                                    stroke={getObjectColor(objectTypes.indexOf(subNode.objectType))}
                                    stroke-width={5 * k}
                                    fill="white"
                                    id={node.name}
                                    rank={node.rank}
                                    order={node.order}
                                    is_backbone={node.is_backbone}
                                    ></circle>)
                            }
                        }
                    })
                }
            }
        });

        // A->B and B->A of one object type arrive as a single edge (reverse_freq set): two arrowheads
        Object.keys(edges).forEach((key) => {
            const edge = edges[key];
            const reverse = edge.reverse_freq != null ? { freq: edge.reverse_freq } : null;
            const from = edge.source, to = edge.target;
            const freq = reverse ? Math.max(edge.freq, reverse.freq) : edge.freq;
            const colorIdx = objectTypes.indexOf(edge.object_type);
            const info = reverse
                ? [`${from} ⇄ ${to}`, `object type: ${edge.object_type}`, `${from} → ${to}: ${edge.freq}`, `${to} → ${from}: ${reverse.freq}`]
                : [`${from} → ${to}`, `object type: ${edge.object_type}`, `frequency: ${edge.freq}`];

            const d = roundedPath(edge.data, 80 * k, R + ARROW_LEN, reverse ? R + ARROW_LEN : 0);
            // animate from the previous position of the same edge (same chain length, as ranks are fixed)
            const prevEdge = prevData && prevData.edges[key];
            const prevD = prevEdge && prevEdge.data.length === edge.data.length
                ? roundedPath(prevEdge.data, 80 * k, R + ARROW_LEN, reverse ? R + ARROW_LEN : 0) : null;

            edgeList.push(<path
                className="edge"
                d={d}
                fill="none"
                stroke={getObjectColor(colorIdx)}
                stroke-width={getEdgeWidth(maxFreq, minFreq, freq, k)}
                opacity={getEdgeOpacity(maxFreq, minFreq, freq)}
                stroke-linejoin="round"
                stroke-linecap="butt"
                marker-end={`url(#arrow-${colorIdx})`}
                marker-start={reverse ? `url(#arrow-${colorIdx})` : undefined}
                id={edge.key}
                onClick={(e) => { e.stopPropagation(); setEdgeInfo({lines: info, color: getObjectColor(colorIdx), x: e.clientX, y: e.clientY}); }}
            >{prevD ? <animate attributeName="d" dur={animationSeconds} from={prevD} to={d} fill="freeze" /> : null}</path>)
        });

        // The view box covers the full (unfiltered) layout as well as the current one, so a
        // filtered layout is shown in the same frame and its re-centring by the backend is visible.
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        const layouts = originalOutput && originalOutput !== data ? [originalOutput, data] : [data];
        layouts.forEach(layout => Object.values(layout.nodes).forEach(node => {
            Object.values(node.nodes_visualized).forEach(sub => {
                minX = Math.min(minX, sub.x - sub.r); maxX = Math.max(maxX, sub.x + sub.r);
                minY = Math.min(minY, sub.y - sub.r); maxY = Math.max(maxY, sub.y + sub.r);
            });
            if (node.is_real) {
                const addon = node.object_types.length - node.object_types.indexOf(node.object_axis);
                maxX = Math.max(maxX, node.x + 2 * R * addon + 340 * k);   // label foreignObject
            }
        }));
        const pad = 60 * k;
        const viewBox = `${minX - pad} ${minY - pad} ${maxX - minX + 2 * pad} ${maxY - minY + 2 * pad}`;

        const pl = <div id="svg-container">
                <svg
                    viewBox={viewBox}
                    width="100%"
                    style={{height: 'auto', display: 'block'}}
                    xmlns="http://www.w3.org/2000/svg"
                    fill="white"
                >
                    <defs>
                        {/* one arrowhead per object type colour; fixed size (not scaled by the edge width),
                            tip exactly at the end of the path, i.e. on the node border */}
                        {objectTypes.map((ot, i) => (
                            <marker
                              key={ot}
                              id={`arrow-${i}`}
                              viewBox="0 0 10 10"
                              refX="0"
                              refY="5"
                              markerUnits="userSpaceOnUse"
                              markerWidth={ARROW_LEN}
                              markerHeight={ARROW_LEN}
                              orient="auto-start-reverse">
                              <path d="M 0 0 L 10 5 L 0 10 z" fill={getObjectColor(i)} stroke="#fff" stroke-width="0.6" />
                            </marker>
                        ))}
                    </defs>
                    <g>
                        {edgeList}
                    </g>
                    <g>
                        {nodeList}
                    </g>
                    <g>
                        {nodeNameList}
                    </g>
                </svg>
            </div>
        setProcessLayout(pl);
    }

    return (
        <div className="process-model-visualization" style={{position: 'absolute',
            inset: 0,
            overflowX: 'hidden',
            overflowY: 'auto'}}>
            { loaderOn ?
                // full-window overlay above everything (controls are z-index 2, floating bar 1)
                <div id="screener" style={{position: 'fixed', inset: 0, zIndex: 10,
                    backgroundColor: 'rgba(163, 181, 192, 0.6)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                    <Button style={{position: 'absolute', top: '72px', right: '12px', minWidth: 0}} onClick={()=>removeLoader()}>
                        <CloseIcon style={{fontSize: '32px', color: '#000'}} />
                    </Button>
                    <GradientCircularProgress />
                </div> : null
            }

            <div style={{padding: '0 20px 8px', fontSize: '12px'}}>
                {/* Data / Object Types stay at the top while the drawing scrolls */}
                <div style={{position: 'sticky', top: 0, zIndex: 2, background: '#fff', padding: '8px 0 4px'}}>
                <div style={{display: 'table'}}>
                    <span style={{'font-weight': 'bold',
                    'padding-right': '12px',
                    display: 'table-cell',
                    'vertical-align': 'middle'}}>Data</span>
                    <FormControl size="small" sx={{ m: 0.5, minWidth: 120 }} style={{width: '300px'}}>
                        <InputLabel sx={{fontSize: 12}}>OCEL data to visualize</InputLabel>
                        <Select
                          size="small"
                          sx={{fontSize: 12}}
                          labelId="demo-simple-select-helper-label"
                          id="demo-simple-select-helper"
                          value={dataSelected}
                          onChange={handleChange}
                        >
                        {data.map((d, i)=> (
                            <MenuItem value={i} sx={{fontSize: 12}}>{d}</MenuItem>
                        ))}

                        </Select>
                    </FormControl>

                    <span style={{display: 'table-cell', 'vertical-align': 'middle'}}>
                        <Button size="small" onClick={()=>getCoordination()} variant="contained">Visualize</Button>
                    </span>

                </div>
                <Divider />

                <Divider />

                <Divider />

                {selectedTypes.length > 0 ?
                <div>
                    <span style={{'font-weight': 'bold', 'padding-right': '12px', display: 'table-cell', 'vertical-align': 'middle'}}>Object Types</span>
                    {objectTypes.map((oType, index) => (
                        <span style={{display: 'table-cell', 'vertical-align': 'middle'}}>
                            <FormControlLabel control={<Checkbox checked={!!selectedTypes[index]} onChange={(e)=>toggleObjectType(e, index)} sx={{
                                color: '#' + KELLYCOLORS[index],
                                "&.Mui-checked": {
                                    color: '#' + KELLYCOLORS[index],
                                },
                            }} size="small" />} label={oType} componentsProps={{typography: {fontSize: 12}}} />
                        </span>
                    ))}
                    <span style={{display: 'table-cell', 'vertical-align': 'middle'}}>
                        <Button size="small" onClick={()=>applyFilters()} variant="contained">Apply</Button>

                    </span>
                    <Divider />
                </div> : null}
                </div>

                <div id="main-container" style={{position: 'relative', width: '100%'}}>
                    { processLayout ?
                    <div className="filtering-bar" style={{boxShadow: 'rgba(0, 0, 0, 0.35) 0px 5px 15px',
                        textAlign: 'center',
                        zIndex: 1,
                        padding: '8px 8px 12px',
                        position: 'fixed',
                        top: '165px',
                        right: '30px',
                        background: '#fff',
                        borderRadius: '6px',
                        fontSize: '12px'}}>
                        {/* two vertical sliders in the same style: zoom | edge filtering */}
                        <div style={{display: 'flex', gap: '12px', alignItems: 'flex-start'}}>
                            <div>
                                <div style={{fontWeight: 'bold'}}>Zoom</div>
                                <Box sx={{ width: 90, height: 440, padding: '12px 8px 16px', margin: '0 auto',
                                           '& .MuiSlider-markLabel': {fontSize: 11} }}>
                                    <Slider
                                        sx={{ '& input[type="range"]': { WebkitAppearance: 'slider-vertical' } }}
                                        orientation="vertical"
                                        aria-label="Zoom"
                                        value={zoom}
                                        getAriaValueText={(v) => `${v}%`}
                                        valueLabelDisplay="auto"
                                        step={5}
                                        min={ZOOM_MIN}
                                        max={ZOOM_MAX}
                                        marks={[10, 50, 100, 150, 200].map(v => ({value: v, label: `${v}%`}))}
                                        onChange={(e, v) => zoomKeepingCenter(v)}
                                    />
                                </Box>
                                <Button size="small" variant="contained" onClick={fitView}>Reset</Button>
                            </div>
                            <div>
                                <div style={{fontWeight: 'bold'}}>Edge filtering</div>
                                <Box sx={{ width: 90, height: 440, padding: '12px 8px 16px', margin: '0 auto',
                                           '& .MuiSlider-markLabel': {fontSize: 11} }}>
                                    <Slider
                                        sx={{ '& input[type="range"]': { WebkitAppearance: 'slider-vertical' } }}
                                        orientation="vertical"
                                        aria-label="Edge filtering"
                                        value={filterValue}
                                        getAriaValueText={(v) => `${v}%`}
                                        valueLabelDisplay="auto"
                                        shiftStep={10}
                                        step={10}
                                        min={0}
                                        max={100}
                                        marks={[0, 20, 40, 60, 80, 100].map(v => ({value: v, label: `${v}%`}))}
                                        onChange={(e, v) => setFilterValue(v)}
                                    />
                                </Box>
                                <Button size="small" variant="contained" onClick={()=>applyFilters()}>Apply</Button>
                            </div>
                        </div>
                        <div style={{fontSize: '11px', color: '#666', marginTop: '6px'}}>Ctrl + wheel to zoom</div>
                    </div> : null
                    }

                    <div style={{marginRight: '240px', overflowX: 'auto'}} onClick={() => setEdgeInfo(null)}>
                        <div ref={drawingRef} style={{width: `${zoom}%`, margin: "0 auto"}}>
                            {processLayout}
                        </div>
                    </div>

                    {edgeInfo ?
                    <div style={{position: 'fixed', left: edgeInfo.x + 12, top: edgeInfo.y + 12, zIndex: 2,
                                 background: '#fff', border: `2px solid ${edgeInfo.color}`, borderRadius: '6px',
                                 boxShadow: 'rgba(0, 0, 0, 0.25) 0px 3px 10px', padding: '8px 12px',
                                 fontSize: '12px', lineHeight: 1.6, whiteSpace: 'nowrap'}}>
                        <div style={{fontWeight: 'bold'}}>{edgeInfo.lines[0]}</div>
                        {edgeInfo.lines.slice(1).map((line, i) => <div key={i}>{line}</div>)}
                    </div> : null}

                </div>
            </div>

        </div>

    );
}