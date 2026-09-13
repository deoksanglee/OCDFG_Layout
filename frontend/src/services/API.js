import axios from 'axios';

const API_HOST = process.env.REACT_APP_API_HOST || 'http://localhost:8000'

export const getDataList = async() => {
	const response = await axios.get(`${API_HOST}/ocel-list`);
	return response.data;
}

export const removeData = async(name) => {
	const response = await axios.delete(`${API_HOST}/ocel-remove`, {
		data: { data_name: name }
	});
	return response.data;
}

export const uploadData = async(name, data) => {
	const response = await axios.post(`${API_HOST}/ocel-upload`, {
		data_name: name,
		d: data
	});
	return response.data;
}

export const getDataInfo = async(name) => {
	const response = await axios.get(`${API_HOST}/ocel-info`, { params: { data_name: name } });
	return response.data;
}

// Compute the full layout of an uploaded log. Returns { output, pickle_path, layout_time_seconds }.
export const getCoord = async(data_dir) => {
	const response = await axios.get(`${API_HOST}/ocel-process-layout`, { params: { data_dir } });
	return response.data;
}

// Object-type selection + frequency filter combined, on the cached layout.
// object_types: array of names to keep (null = all); filter_value: 0~100 (null = all edges)
export const getFilteredLayout = async (pickle_path, object_types, filter_value) => {
	const response = await axios.post(`${API_HOST}/filter-layout`, { pickle_path, object_types, filter_value });
	return response.data;
};
