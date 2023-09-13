import requests
import json
import numpy as np
from scipy.optimize import linear_sum_assignment
import folium
from itertools import permutations
from ortools.linear_solver import pywraplp
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import time

class TravelTimeCalculator:
    def __init__(self, API_KEY):
        self.API_KEY = API_KEY
        self.mode_mapping = {
            "driving": "driving-car",
            "walking": "foot-walking",
            "cycling": "cycling-regular",
            #"transit": "transit"  # Did not find a way to make it work
        }

    def get_travel_time(self, locations, mode):
        # Use the OpenStreetMap API to get the coordinates of the locations
        coordinates = []
        for location in locations:
            response = requests.get(f"http://nominatim.openstreetmap.org/search?q={location}&format=json")
            coordinates.append((json.loads(response.text)[0]['lon'], json.loads(response.text)[0]['lat']))

        # Use the OpenRouteService Matrix API to get the travel times between the locations
        headers = {
            'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
            'Authorization': self.API_KEY,
            'Content-Type': 'application/json; charset=utf-8'
        }
        body = {
            'locations': coordinates,
            'profile': self.mode_mapping[mode],
            'metrics': ['duration']
        }

        matrix_response = requests.post(f'https://api.openrouteservice.org/v2/matrix/{self.mode_mapping[mode]}', headers=headers, data=json.dumps(body))

        # Check if the request was successful
        if matrix_response.status_code == 200:
            # Extract the travel times from the response
            travel_times = json.loads(matrix_response.text)['durations']

            # Return the matrix of travel times
            return travel_times
        else:
            print(f"Error: {matrix_response.status_code}")
            print(matrix_response.text)
            return None

    def get_route(self, origin, destination, mode):
        # Use the OpenStreetMap API to get the coordinates of the origin and destination
        origin_response = requests.get(f"http://nominatim.openstreetmap.org/search?q={origin}&format=json")
        destination_response = requests.get(f"http://nominatim.openstreetmap.org/search?q={destination}&format=json")

        # Check if the API returned results for the origin and destination
        origin_coordinates = json.loads(origin_response.text)
        destination_coordinates = json.loads(destination_response.text)
        if not origin_coordinates or not destination_coordinates:
            print(f"No results found for origin: {origin} or destination: {destination}")
            print(f"Impossible Route: {origin} -> {destination}")
            return None

        # Use the OpenRouteService API to get the route between the origin and destination
        headers = {
            'Accept': 'application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8',
            'Authorization': self.API_KEY,
            'Content-Type': 'application/json; charset=utf-8'
        }
        body = {
            'coordinates': [
                [origin_coordinates[0]['lon'], origin_coordinates[0]['lat']],
                [destination_coordinates[0]['lon'], destination_coordinates[0]['lat']]
            ],
            'profile': self.mode_mapping[mode],
            'format': 'geojson'
        }

        route_response = requests.post(f'https://api.openrouteservice.org/v2/directions/{self.mode_mapping[mode]}/geojson', headers=headers, data=json.dumps(body))

        # Check if the 'features' key exists in the response
        route_data = json.loads(route_response.text)
        if 'features' not in route_data:
            print(f"Error: 'features' key not found in the route response for origin: {origin} and destination: {destination}")
            print("Response content:", route_response.text)
            return None

        # Extract the route from the response
        route = route_data['features'][0]['geometry']['coordinates']

        return route

    def visualize_tsp_tour(self, locations, tour, mode, total_duration, ordered_locations):
        all_cordinates_of_route = []

        m = folium.Map(zoom_start=2)

        for i in range(len(tour) - 1):
            route = self.get_route(locations[tour[i]], locations[tour[i+1]], mode)
            if route is None:
                print(f"Impossible Route: {locations[tour[i]]} -> {locations[tour[i+1]]}")
                return None
            route = [(p[1], p[0]) for p in route]
            all_cordinates_of_route.extend(route)

            folium.Marker(location=route[0], popup=locations[tour[i]]).add_to(m)
            folium.PolyLine(route, color="red", weight=2.5, opacity=1).add_to(m)

        route = [(p[1], p[0]) for p in self.get_route(locations[tour[-1]], locations[tour[0]], mode)]
        if route is None:
            print(f"Impossible Route: {locations[tour[-1]]} -> {locations[tour[0]]}")
            return None
        
        folium.Marker(location=route[0], popup=locations[tour[-1]]).add_to(m)
        folium.PolyLine(route, color="red", weight=2.5, opacity=1).add_to(m)

        avg_lat = sum(p[0] for p in all_cordinates_of_route) / len(all_cordinates_of_route)
        avg_lon = sum(p[1] for p in all_cordinates_of_route) / len(all_cordinates_of_route)
        m.location = [avg_lat, avg_lon]

        m.fit_bounds([[min(p[0] for p in all_cordinates_of_route), min(p[1] for p in all_cordinates_of_route)], 
                    [max(p[0] for p in all_cordinates_of_route), max(p[1] for p in all_cordinates_of_route)]])

        # Information box on the left
        hours = int(round(total_duration // 60))
        minutes = int(round(total_duration % 60, 0))

        info_html = f"""
        <div style="position: absolute; top: 0; left: 0; width: 15%; height: 100%; background-color: white; padding: 10px; border-right: 1px solid black; overflow-y: auto;">
            <h4>Travel Details</h4>
            <p><b>Total Duration:</b> {hours} hours {minutes} minutes<br></p>
            <p><b>Visit in order:</b></p>
            <ol>
        """
        for location in ordered_locations:
            info_html += f"<li>{location}</li>"
        info_html += "</ol></div>"

        # Adjust the map container to occupy 85% width on the right side
        map_html = """
            <div style="position: absolute; top: 0; right: 0; width: 85%; height: 100%;">
        """
        map_html += m.get_root().render()
        map_html += "</div>"

        final_html = '<meta charset="UTF-8">' + info_html + map_html

        with open('temp_route_visualization.html', 'w', encoding='utf-8') as f:
            f.write(final_html)

        return all_cordinates_of_route

class TSPMethod:
    def __init__(self, distance_matrix):
        self.distance_matrix = np.array(distance_matrix)

    def solve(self, max_time_seconds):
        # This method should be overridden in subclasses and return True/False if optimal route was found and the tour itself 
        raise NotImplementedError("This method should be overridden in subclasses")
    
class TwoOptMethod(TSPMethod): 
    def solve(self, max_time_seconds):
        start_time = time.time()  # Record the start time

        self.distance_matrix = self.distance_matrix.astype(int)  # Convert to integers

        # Step 1: Initial solution using the Hungarian method
        rows, cols = linear_sum_assignment(self.distance_matrix)
        initial_tour = np.append(cols, cols[0])  # Create an initial tour

        # Step 2: Optimize the tour with 2-opt algorithm
        optimized_tour, optimal = self._two_opt(initial_tour, start_time, max_time_seconds)

        return optimal, optimized_tour

    def _two_opt(self, tour, start_time, max_time_seconds):
        num_cities = len(tour)
        optimal = True  # Initialize as True, will set to False if time limit is reached
        for i in range(num_cities - 1):
            for j in range(i + 2, num_cities - 1):
                # Check if the time limit has been reached
                elapsed_time = time.time() - start_time
                if elapsed_time > max_time_seconds:
                    print("Time limit reached.")
                    optimal = False  # Set optimal to False as time limit is reached
                    return tour, optimal
                # Don't swap first and last edge
                if i == 0 and j == num_cities - 2:
                    continue

                old_distance = self.distance_matrix[tour[i], tour[i + 1]] + self.distance_matrix[tour[j], tour[j + 1]]
                new_distance = self.distance_matrix[tour[i], tour[j]] + self.distance_matrix[tour[i + 1], tour[j + 1]]
                
                # If the swap gives a shorter tour, do it
                if new_distance < old_distance:
                    tour[i + 1 : j + 1] = tour[j : i : -1]

        return tour, optimal
    
class PermutationsMethod(TSPMethod):
    def solve(self, max_time_seconds):
        start_time = time.time()  # Record the start time

        n = self.distance_matrix.shape[0]
        best_tour = None
        best_distance = np.inf
        optimal = True  # Initialize as True, will set to False if time limit is reached

        for tour in permutations(range(n)):
            # Check if the time limit has been reached
            
            elapsed_time = time.time() - start_time
            if elapsed_time > max_time_seconds:
                print("Time limit reached.")
                optimal = False  # Set optimal to False as time limit is reached
                return optimal, best_tour  # Return the best tour found so far and optimal status

            distance = sum(self.distance_matrix[tour[i-1], tour[i]] for i in range(n))
            if distance < best_distance:
                best_distance = distance
                best_tour = tour

        # Add the first city to the end of the tour
        best_tour = np.append(best_tour, best_tour[0])

        return optimal, np.array(best_tour)  # Return the best tour and whether it's optimal

class FlowBasedMethod(TSPMethod):
    def solve(self, max_time_seconds):
        self.distance_matrix = self.distance_matrix.astype(int)  # integers required by SCIP
        np.fill_diagonal(self.distance_matrix, np.iinfo(np.int32).max)  # Discourage staying in the same city
        n = self.distance_matrix.shape[0]
        
        # Create the linear solver
        solver = pywraplp.Solver.CreateSolver('SCIP')
        
        # Set the time limit in milliseconds
        solver.set_time_limit(int(max_time_seconds * 1000))

        # Create variables
        x = {}
        for i in range(n):
            for j in range(n):
                x[i, j] = solver.IntVar(0, 1, f'x_{i}_{j}')

        u = [solver.IntVar(0, n, f'u_{i}') for i in range(n)]

        # Constraints
        for i in range(n):
            solver.Add(solver.Sum(x[i, j] for j in range(n)) == 1)  # each city must be departed from exactly once
            solver.Add(solver.Sum(x[j, i] for j in range(n)) == 1)  # each city must be visited exactly once

        for i in range(1, n):
            for j in range(1, n):
                if i != j:
                    solver.Add(u[i] - u[j] + n * x[i, j] <= n - 1)  # subtour elimination

        # Objective function: minimize the total distance
        solver.Minimize(solver.Sum(self.distance_matrix[i, j] * x[i, j] for i in range(n) for j in range(n)))

        # Solve the problem
        status = solver.Solve()

        # Initialize tour list with the first city
        tour = [0]

        # Extract the tour if a solution exists
        if status == pywraplp.Solver.OPTIMAL:
            optimal = True
        else:
            optimal = False  # Assume time limit reached if not OPTIMAL
            if status != pywraplp.Solver.FEASIBLE:
                print("No solution found")
                return False, None

        # Start from the first city
        current_city = 0
        while len(tour) < n:
            # Go to the next city
            for j in range(n):
                if x[current_city, j].solution_value() > 0.5:
                    tour.append(j)
                    current_city = j
                    break
        # Add the first city to the end of the tour
        tour.append(0)

        if not optimal:
            print("Time limit reached.")

        return optimal, np.array(tour)

class ConstraintProgrammingMethod(TSPMethod):
    def solve(self, max_time_seconds):
        self.distance_matrix = self.distance_matrix.astype(int)
        n = self.distance_matrix.shape[0]

        # Create the routing model
        manager = pywrapcp.RoutingIndexManager(n, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        # Create the distance callback
        def distance_callback(i, j):
            return self.distance_matrix[manager.IndexToNode(i), manager.IndexToNode(j)]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)

        # Define cost of each arc
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Set parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.time_limit.seconds = max_time_seconds
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

        # Solve the problem
        solution = routing.SolveWithParameters(search_parameters)

        # Initialize tour list
        tour = []

        # Determine if the solution is optimal
        optimal = (solution is not None)

        # Extract the tour if a solution exists
        if solution:
            index = routing.Start(0)
            while not routing.IsEnd(index):
                tour.append(manager.IndexToNode(index))
                index = solution.Value(routing.NextVar(index))
            # Add the first city to the end of the tour
            tour.append(0)

        if not optimal:
            print("Time limit reached.")

        return optimal, np.array(tour) if tour else None

class TSPMethodFactory:
    #add new methods here
    methods = {
        "TwoOpt": TwoOptMethod,
        "Permutations": PermutationsMethod,
        "FlowBased": FlowBasedMethod,
        "ConstraintProgramming": ConstraintProgrammingMethod
    }

    @classmethod
    def create_method(cls, method_name, distance_matrix):
        if method_name in cls.methods:
            return cls.methods[method_name](distance_matrix)
        else:
            raise ValueError(f"Unknown method: {method_name}")

class TSPSolver:
    def __init__(self, distance_matrix, method):
        self.distance_matrix = np.array(distance_matrix)
        self.method = method

    def solve_tsp(self, max_time_seconds):
        return self.method.solve(max_time_seconds)
    
    def get_travel_time(self, tour):
        return sum(self.distance_matrix[tour[i-1], tour[i]] for i in range(1, len(tour)))

    def pretty_print(self, tour, locations):
        route = " -> ".join(str(i) for i in tour)
        print("Best order: ", route)
        # Create a route string with the location names instead of their indices
        route = " -> ".join(locations[i] for i in tour)
        print("Best route: ", route)

        # Calculate the total travel time in minutes
        total_time_minutes = self.get_travel_time(tour) / 60

        # Convert the total time to hours and minutes
        hours = int(total_time_minutes // 60)
        minutes = int(total_time_minutes % 60)

        if hours > 0:
            print(f"Total Duration: {hours} hour(s) and {minutes} minute(s)")
        else:
            print(f"Total Duration: {minutes} minute(s)")

class TSPSolverInterface:
    def __init__(self, API_KEY):
        self.calculator = TravelTimeCalculator(API_KEY)

    def solve_tsp(self, locations, mode, method_name, max_time_seconds):
        # Calculate travel times
        travel_times = self.calculator.get_travel_time(locations, mode)
        print("cost Matrix", travel_times)
        if not any(None in sublist for sublist in travel_times):
            # Check the selected method and create the appropriate method instance
            method = TSPMethodFactory.create_method(method_name, travel_times)

            solver = TSPSolver(travel_times, method)
            
            optimal, tour = solver.solve_tsp(max_time_seconds)
            if tour is None:
                return False, None, None, None
            solver.pretty_print(tour, locations)  # Pass locations to pretty_print method
            total_time_minutes = solver.get_travel_time(tour) / 60
            ordered_locations = [locations[i] for i in tour]

            # Visualize the tour
            route = self.calculator.visualize_tsp_tour(locations, tour, mode, total_time_minutes, ordered_locations)

            # Return the locations in the order they should be visited
            return optimal, ordered_locations, total_time_minutes, route
        else:
            print('No travel times were obtained for the following connections:')
            for i in range(len(travel_times)):
                for j in range(len(travel_times[i])):
                    if travel_times[i][j] is None:
                        print(f"{locations[i]} -> {locations[j]}")
            return None, None, None, None