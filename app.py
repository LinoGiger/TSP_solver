from dash import Dash, dcc, html, Input, Output, State, dash, ALL, callback_context
import dash_leaflet as dl
import requests
import json
from tsp_logic import TSPSolverInterface
import os
import folium
import webbrowser
import tkinter as tk

dir_path = os.path.dirname(os.path.realpath(__file__))
os.chdir(dir_path)
API_KEY = open('API_KEY.txt', 'r').read()


TSPInterface = TSPSolverInterface(API_KEY)

external_stylesheets = [{
    'href': 'https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css',
    'rel': 'stylesheet',
}]
app = Dash(__name__, external_stylesheets=external_stylesheets)


app.layout = html.Div([
    html.Div([
        html.Div([
            html.Div([
                html.Label('Location:'),
                dcc.Input(type='text', id='location', name='location'),
                html.Button('Search', id='search-button', n_clicks=0),
                html.Div(id='error-message', style={'color': 'red'}),
            ]),
            
            html.Label('Locations:'),
            html.Div(id='locations-list'),
            
            html.Label('Mode of transport:'),
            dcc.Dropdown(
                id='transport',
                options=[
                    {'label': 'Driving', 'value': 'driving'},
                    {'label': 'Walking', 'value': 'walking'},
                    {'label': 'Cycling', 'value': 'cycling'},
                ],
                value='driving'
            ),

            html.Label('TSP Solving Method:'),
            dcc.Dropdown(
                id='method', # Add new methods here
                options=[
                    {'label': 'TwoOpt', 'value': 'TwoOpt'},
                    {'label': 'Permutations', 'value': 'Permutations'},
                    {'label': 'FlowBased', 'value': 'FlowBased'},
                    {'label': 'ConstraintProgramming', 'value': 'ConstraintProgramming'},
                ],
                value='TwoOpt'
            ),
            html.Div([
            html.Label('Time Limit (seconds):', style={'marginRight': '10px'}),
            dcc.Input(type='number', id='time-limit', min=0, step=1, value=60, style={'textAlign': 'right', 'width': '15%'}),  # Adjusted width to 50%
            ], style={'marginTop': '10px', 'display': 'flex', 'alignItems': 'center'}),

            html.Button('Submit', id='submit-button', n_clicks=0, style={'marginTop': '10px'}),
            html.Button('Open in new Tab', id='open-tab-button', n_clicks=0, style={'marginLeft': '10px'}),
            html.Button('Save Route', id='save-route-button', n_clicks=0, style={'marginLeft': '10px'}),
            html.Div(
            dcc.Loading(
                id="loading",
                type="dot",
                children=[
                    html.Div([html.Strong(id='info')]),  # This is where information about the route will be displayed if nessesary 
                    html.Div(id='path-display'),  # This is where the path will be displayed
                    html.Div(id='travel-time-display') # This is where the travel time will be displayed
                ]
            ),
            style={'marginTop': '20px'}  # Add some margin at the top
        ),
        ],
        id='inputForm'),
    ],
    id='sidebar', style={'float': 'left', 'width': '30%', 'height': '100%', 'overflow': 'auto', 'padding': '10px', 'box-sizing': 'border-box', 'border-right': '1px solid #ccc'}),

    dl.Map(id='map', style={'float': 'right', 'width': '70%', 'height': '100vh', 'position': 'relative', 'z-index': 0}, center=[0, 0], zoom=2, children=[
        dl.TileLayer(url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
    ]),
    html.Div(id='map-marker-store', style={'display': 'none'}),  # Hidden div to store the updated map marker
    html.Div(id='locations-store', style={'display': 'none'}),  # Hidden div to store the added locations
], style={'height': '100vh'})

@app.callback(
    [Output('locations-store', 'children'),
     Output('map-marker-store', 'children'),
     Output('location', 'value'),
     Output('map', 'bounds'),
     Output('error-message', 'children')],
    [Input('search-button', 'n_clicks'),
     Input({'type': 'delete-button', 'index': ALL}, 'n_clicks')],
    [State('location', 'value'),
     State('locations-store', 'children')],
    prevent_initial_call=True
)
def update_locations(n_clicks, delete_n_clicks, location, locations_json):
    ctx = callback_context
    locations = json.loads(locations_json) if locations_json else []

    if ctx.triggered:
        button_id_str = ctx.triggered[0]['prop_id'].split('.')[0]
        try:
            button_id = json.loads(button_id_str)  # Try to parse the string as JSON
        except json.JSONDecodeError:
            button_id = button_id_str  # If it's not a valid JSON string, then it must be the 'search-button'

        if button_id == 'search-button':
            if n_clicks and location:
                try:
                    response = requests.get(f"http://nominatim.openstreetmap.org/search?q={location}&format=json")
                    json_response = response.json()
                    if json_response:
                        latitude = float(json_response[0]['lat'])
                        longitude = float(json_response[0]['lon'])
                        new_marker_position = [latitude, longitude]
                        locations.append({'name': location, 'position': new_marker_position})
                        bounds = compute_bounds(locations)  # Compute bounds after adding the new location
                        return json.dumps(locations), json.dumps(locations), "", bounds, ""  # Also update the map-marker-store
                    else:
                        print("Location not found")
                except Exception as e:
                    print("Error occurred during geocoding:", e)

        elif 'type' in button_id and button_id['type'] == 'delete-button':
            index_to_delete = button_id['index']
            del locations[index_to_delete]
            bounds = compute_bounds(locations)
            return json.dumps(locations), json.dumps(locations), dash.no_update, bounds, ""  # Also update the map-marker-store

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, "Location not found"  # Show error message

def compute_bounds(locations):
    if locations:
        lats = [loc['position'][0] for loc in locations]
        lngs = [loc['position'][1] for loc in locations]

        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)
        
        return [[min_lat, min_lng], [max_lat, max_lng]]
    else:
        return dash.no_update  # Default bounds, can be adjusted as needed

@app.callback(
    Output('locations-list', 'children'),
    Input('locations-store', 'children')
)
def update_locations_list(locations_json):
    locations = json.loads(locations_json) if locations_json else []
    return html.Ul([html.Li([location['name'], html.Button('X', id={'type': 'delete-button', 'index': i})]) for i, location in enumerate(locations)])  # Create a list item for each location with a delete button

#General callback for updating the map - needs to be all in one function because of Dash limitations
@app.callback(
    [Output('info', 'children'),
     Output('path-display', 'children'),
     Output('travel-time-display', 'children'),
     Output('map', 'children'),],
    [Input('submit-button', 'n_clicks'),
     Input('map-marker-store', 'children'),
     Input('open-tab-button', 'n_clicks'),
     Input('save-route-button', 'n_clicks')],
    [State('locations-store', 'children'),
     State('transport', 'value'),
     State('method', 'value'),
     State('time-limit', 'value'),
     State('map', 'children'),
     State('path-display', 'children')],
    prevent_initial_call=True
)
def combined_callback(submit_n_clicks, marker_store, open_tab_n_clicks, save_route_n_clicks, locations_json, transport_mode, tsp_method, time_limit, map_children, current_path_display):
    ctx = callback_context

    # Check if the submit-button was clicked
    if ctx.triggered[0]['prop_id'] == 'submit-button.n_clicks':
        # Parse the locations from the stored JSON string
        locations = json.loads(locations_json) if locations_json else []

        # Check if there are less than 2 locations
        if len(locations) < 2:
            return "Please add at least two locations to compute a route.", "", "", dash.no_update

        # Extract the names of the locations
        location_names = [location['name'] for location in locations]
        # Call the TSPSolverInterface's solve_tsp method
        optimal, ordered_locations, total_time_for_route, route = TSPInterface.solve_tsp(location_names, transport_mode, tsp_method, time_limit)

        if route is None:
            return "Impossible Route or error in request. Check Terminal for additional information.", "", "", dash.no_update

        # Format the ordered locations into a readable string
        path_string = ' -> '.join(ordered_locations)

        # Display the total time for the route
        hours = int(total_time_for_route // 60)
        minutes = int(total_time_for_route % 60)

        if hours > 0:
            travel_time_string = f"Total Duration: {hours} hour(s) and {minutes} minute(s)"
        else:
            travel_time_string = f"Total Duration: {minutes} minute(s)"

        # Remove any existing polyline
        map_children = [child for child in map_children if child['type'] != 'Polyline']

        # Add the new route to the map
        polyline = dl.Polyline(positions=route, color="red", weight=2.5, opacity=1)
        map_children.append(polyline)

        if optimal:
            return "Optimal Route Found", path_string, travel_time_string, map_children
        else:
            return "Suboptimal Route Found, solver didn't finish", path_string, travel_time_string, map_children

    # Check if the open-tab-button was clicked
    elif ctx.triggered[0]['prop_id'] == 'open-tab-button.n_clicks':
        # Check if there is a path to display or a message indicating that the user should generate a route first
        if not current_path_display or current_path_display.startswith("Please"):
            return "Please generate Route first.", dash.no_update, dash.no_update, dash.no_update
        webbrowser.open('temp_route_visualization.html', new=2)
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    elif ctx.triggered[0]['prop_id'] == 'save-route-button.n_clicks':
        return save_route(locations_json, current_path_display)

    else:
        # Handle the logic for updating markers
        locations = json.loads(marker_store) if marker_store else []
        markers = [dl.Marker(position=location['position'], children=[dl.Tooltip(location['name'])]) for location in locations]
        non_marker_children = [child for child in map_children if child['type'] != 'Marker']
        map_children = non_marker_children + markers

        return dash.no_update, dash.no_update, dash.no_update, map_children

def save_route(locations_json, current_path_display):
    # Check if there is a path to display or a message indicating that the user should generate a route first
    if not current_path_display or current_path_display.startswith("Please"):
        return "Please generate Route first.", dash.no_update, dash.no_update, dash.no_update
    
    file_name = get_user_input()
    if not file_name:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # Ensure the "saved_routes" directory exists
    saved_routes_dir = os.path.join(dir_path, "saved_routes")
    os.makedirs(saved_routes_dir, exist_ok=True)

    source_path = os.path.join(dir_path, 'temp_route_visualization.html')
    destination_path = os.path.join(saved_routes_dir, f'{file_name}.html')

    # take temp_route_visualization.html and copy it to the destination path
    with open(source_path, 'r') as source_file, open(destination_path, 'w') as dest_file:
        html_string = source_file.read()
        html_string = html_string.replace('temp_route_visualization', file_name)
        dest_file.write(html_string)
    return f"Route has beenn saved in the 'saved_routes' Folder as '{file_name}.html'", "", "", dash.no_update

def get_user_input():
    # Create the main window
    root = tk.Tk()
    root.title("Input Window")
    
    # Set the window size
    root.geometry("300x150")
    
    # Center the window on the screen
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x_coordinate = (screen_width/2) - (300/2)
    y_coordinate = (screen_height/2) - (150/2)
    root.geometry("+%d+%d" % (x_coordinate, y_coordinate))
    
    # Create a StringVar() to hold the update from the Entry widget
    user_input = tk.StringVar()

    # Function to close the window and set the value
    def on_save():
        user_input.set(entry.get())
        root.quit()

    # Function to handle the window close event
    def on_close():
        user_input.set("")  # You can set a default value here if desired
        root.quit()

    root.protocol("WM_DELETE_WINDOW", on_close)  # Bind the close event to the on_close function

    # Create and pack the widgets
    label = tk.Label(root, text="Enter file name here (without .html):")
    label.pack(pady=10)
    
    entry = tk.Entry(root, textvariable=user_input, width=30)
    entry.pack(padx=20, pady=10)

    save_button = tk.Button(root, text="Save", command=on_save)
    save_button.pack(pady=10)

    root.lift()  # Raise the window to the top of the window stack
    root.attributes('-topmost', True)  # Ensure the window is on top of all other windows
    root.after_idle(root.attributes, '-topmost', False)  # Reset the topmost attribute after window is created

    root.mainloop()
    root.destroy()

    return user_input.get()

if __name__ == '__main__':
    app.run_server(debug=True)