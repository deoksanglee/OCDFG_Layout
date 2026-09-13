import * as React from 'react';
import { useState, useRef, useEffect } from "react";
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import { getDataList, removeData, uploadData } from '../services/API';
import CloseIcon from '@mui/icons-material/Close';

import '../App.css'

export default function DataPreparation() {
	const [files, setFiles] = useState([]);

	useEffect(() => {
		renewDataList()
	}, []);

	const renewDataList = () => {
		getDataList().then(res => {
			setFiles(res['files']);
		}).catch((err) => {
		})
	}

	return (
		<div className="data-preparation">
			<div className="card-container">
				{files.map(f=> (
					<BasicCard name={f} renewDataList={renewDataList}/>
				))}
				<PlusCard renewDataList={renewDataList}/>
			</div>
		</div>
	);
}

function BasicCard(props) {
	const removeFile = (dataName) => {
		removeData(dataName).then(res=>{
			if (res.success) {
				props.renewDataList();
			}
		})
	}

	return (
		<Card sx={{ width: '30%' }} className="data-card">
	      	<CardContent>
	      		<Button style={{float: 'right'}} onClick={()=>{removeFile(props.name)}}>
	      			<span>
	      				<CloseIcon />
	      			</span>
      			</Button>
	        	<Typography variant="h5" component="div">
	          		{props.name}
        		</Typography>
	      	</CardContent>
	      	<CardActions>
	        	<Button size="small">Show detail info</Button>
	      	</CardActions>
	    </Card>
	);
}

function PlusCard(props) {
	const fileInput = useRef();
	var [dataName, setDataName] = useState('');

	// Graph json file upload method
    const jsonFileChange = e => {
    	const fileReader = new FileReader();
        
        fileReader.readAsText(e.target.files[0]);
        fileReader.onload = e => {
            const data = JSON.stringify(JSON.parse(e.target.result));
            uploadData(dataName, data).then(res => {
            	if (res.success) {
            		props.renewDataList();
            		window.alert('Data Upload Success!');
            	} else {
            		window.alert('Data Upload Failed!');
            	}
            });
        };
    }

	return (
		<Card sx={{ width: '30%' }} className="data-card">
			<input
              type="file"
              style={{ display: "none" }}
              ref={ fileInput }
              onChange={ jsonFileChange }
            />
	      <CardContent style={{'text-align': 'center'}}>
	      	<Box
		      component="form"
		      sx={{
		        '& > :not(style)': { m: 1, width: '25ch' },
		      }}
		      noValidate
		      autoComplete="off"
		    >
	      		<TextField label="Data name" variant="outlined" onChange={(e)=>{ setDataName(e.target.value)}} />
	      		<Button variant="contained" onClick={()=>fileInput.current.click()}>Upload data</Button>
	      	</Box>
	      </CardContent>
	    </Card>
	);
}