import { useNavigate, useLocation } from 'react-router-dom';
import { Route, Routes } from "react-router-dom";
import DataPreparation from './pages/DataPreparation';
import OCDFGLayout from './pages/OCDFGLayout';

import * as React from 'react';
import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import CssBaseline from '@mui/material/CssBaseline';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import List from '@mui/material/List';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';

import classNames from 'classnames';

import './App.css';

const drawerWidth = 240;

const PAGES = [
  { label: '1.Data Preparation', path: '/data-preparation' },
  { label: '2.OCDFG Layout', path: '/OCDFG-layout' },
];

export default function Nav() {
  const navigate = useNavigate();
  const location = useLocation();

  // the current page follows the URL, so direct links / reloads highlight the right menu entry
  const currentPage = PAGES.find(p => p.path.toLowerCase() === location.pathname.toLowerCase()) || PAGES[0];

  return (
    <Box sx={{ display: 'flex', 'background-color': '#1976d2 !important' }}>
      <CssBaseline />
      
      <AppBar
        position="fixed"
        sx={{ width: `calc(100% - ${drawerWidth}px)`, ml: `${drawerWidth}px` }}
      >
        <Toolbar>
          <Typography noWrap component="div" sx={{ fontSize: 15, fontWeight: 500 }}>
            {currentPage.label}
          </Typography>
        </Toolbar>
      </AppBar>

      <Drawer
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
          },
        }}
        variant="permanent"
        anchor="left"
      >
        <Toolbar />
        <Divider />
        <List>
          {PAGES.map((page) => (
            <ListItem className={classNames({ 'menu-selected': page === currentPage })}
            key={page.path} disablePadding>
              <ListItemButton onClick={() => navigate(page.path)}>
                <ListItemText primary={page.label} primaryTypographyProps={{fontSize: 12}} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Drawer>
      {/* app bar + page fill exactly one viewport; the page scrolls inside itself */}
      <Box
        component="main"
        sx={{ flexGrow: 1, bgcolor: 'background.default', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
      >
        <Toolbar />
        <Box sx={{ flex: 1, minHeight: 0, position: 'relative' }}>
          <Routes>
            <Route exact path="/" element={<DataPreparation />} />
            <Route path="/data-preparation" element={<DataPreparation />} />
            <Route path="/OCDFG-layout" element={<OCDFGLayout />} />
          </Routes>
        </Box>
      </Box>
    </Box>
  );
}