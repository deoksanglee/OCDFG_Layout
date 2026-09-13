// src/App.js

import React from "react";
import { Route, Routes } from "react-router-dom";
import Nav from './Nav';

export default class App extends React.Component {
  render() {
    return (
      <div className="App">
        <Nav />
      </div>
    )
  }
}