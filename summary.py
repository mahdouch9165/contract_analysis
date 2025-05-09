#!/usr/bin/env python3
import os
import pickle
import json
import numpy as np
from datetime import datetime
from collections import Counter

# Import Dash components
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import dash_cytoscape as cyto
import plotly.express as px
import plotly.graph_objects as go

# Load Cytoscape's grid layout
cyto.load_extra_layouts()

# Import the necessary classes from contract_analysis
from contract_analysis import Contract, ContractFamily, ContractAnalysis

class ContractAnalysisDashboard:
    def __init__(self):
        """Initialize the dashboard data processor"""
        self.pickle_state = None
        self.json_data = None
        self.families = []
        self.family_map = {}  # Maps family ID to family object
        self.graph = {}  # Now using family.id as keys
        
    def load_data(self):
        """Load data from both pickle and JSON sources"""
        self.pickle_state = None
        self.json_data = None

        self._load_pickle_data()
        self._load_json_data()
        
        
        if self.json_data and 'families' in self.json_data:
            # Try to reconstruct families from JSON
            reconstructed = self._reconstruct_families()
            if reconstructed:
                self.families = reconstructed
                # Create family_map from reconstructed families
                self.family_map = {family.id: family for family in self.families}
                # Load graph data if available in JSON
                if 'graph' in self.json_data:
                    self.graph = self.json_data['graph']
                print("Using reconstructed families from JSON data")
                return True
        # Determine the best data source to use
        elif self.pickle_state and 'families' in self.pickle_state:
            self.families = self.pickle_state['families']
            self.family_map = self.pickle_state.get('family_map', {})
            self.graph = self.pickle_state.get('graph', {})
            
            # If family_map doesn't exist (older state files), create it
            if not self.family_map and self.families:
                self.family_map = {family.id: family for family in self.families}
                
            print("Using data from pickle state file")
            print(f"Loaded {len(self.families)} families and graph with {len(self.graph)} entries")
            return True
                
        print("No valid data found")
        return False
        
    def _load_pickle_data(self):
        """Load data from the pickle file"""
        data_dir = "data"
        state_file = "contract_analysis_state.pkl"
        state_path = os.path.join(data_dir, state_file)
        
        if not os.path.exists(state_path):
            return None
        
        try:
            with open(state_path, 'rb') as f:
                self.pickle_state = pickle.load(f)
                timestamp = self.pickle_state.get('timestamp', 'unknown')
                print(f"Successfully loaded state from {timestamp}")
        except Exception as e:
            print(f"Error loading pickle state: {e}")
    
    def _load_json_data(self):
        """Load data from the JSON export file"""
        data_dir = "data"
        export_file = "contract_families.json"
        export_path = os.path.join(data_dir, export_file)
        
        if not os.path.exists(export_path):
            return None
        
        try:
            with open(export_path, 'r') as f:
                self.json_data = json.load(f)
                timestamp = self.json_data.get('timestamp', 'unknown')
                print(f"Successfully loaded JSON data from {timestamp}")
        except Exception as e:
            print(f"Error loading JSON data: {e}")
    
    def _reconstruct_families(self):
        """Reconstruct ContractFamily objects from JSON data"""
        if not self.json_data or 'families' not in self.json_data:
            return []
        
        reconstructed_families = []
        for family_data in self.json_data['families']:
            try:
                # Create ContractFamily from dictionary data
                family = ContractFamily.from_dict(family_data)
                reconstructed_families.append(family)
            except Exception as e:
                print(f"Error reconstructing family: {e}")
        
        print(f"Successfully reconstructed {len(reconstructed_families)} families")
        return reconstructed_families
    
    def get_basic_stats(self):
        """Get basic statistics about the contract families"""
        if not self.families:
            return {}
            
        total_families = len(self.families)
        total_contracts = sum(family.count for family in self.families)
        unique_contract_names = sum(len(family.names) for family in self.families)
        
        return {
            "total_families": total_families,
            "total_contracts": total_contracts,
            "unique_names": unique_contract_names,
            "avg_contracts_per_family": total_contracts/total_families if total_families else 0,
            "single_contract_families": sum(1 for f in self.families if f.count == 1),
            "multi_contract_families": sum(1 for f in self.families if f.count > 1)
        }
    
    def get_family_size_data(self):
        """Get data for family size distribution"""
        if not self.families:
            return [], []
            
        # Count families by size
        size_counts = Counter([family.count for family in self.families])
        
        # Prepare data for histogram
        sizes = list(size_counts.keys())
        counts = list(size_counts.values())
        
        return sizes, counts
    
    def get_name_frequency_data(self):
        """Get data for contract name frequency analysis"""
        if not self.families:
            return []
            
        # Collect all unique names
        all_names = []
        for family in self.families:
            all_names.extend(list(family.names))
        
        # Calculate name frequency
        name_frequency = Counter(all_names)
        top_names = name_frequency.most_common(10)
        
        return top_names
    
    def get_network_data(self):
        """Generate network data for cytoscape visualization using family IDs"""
        if not self.families:
            print("No families found for network visualization")
            return [], []
            
        nodes = []
        edges = []
        
        # Create nodes for each family (using family ID as the node ID)
        for family in self.families:
            # Get a representative name for the family
            names = list(family.names)
            if names:
                name = names[0]
                if len(name) > 15:
                    name = name[:12] + "..."
            else:
                name = f"Family {family.id[:8]}"
                
            # Determine node size based on contract count
            size = max(20, min(100, 20 + family.count * 5))
            
            # Create node
            nodes.append({
                'data': {
                    'id': family.id,  # Use family.id instead of index
                    'label': name,
                    'size': size,
                    'contract_count': family.count,
                    'name_count': len(family.names),
                    'addresses': len(family.addresses),
                    'names': list(family.names)[:5],  # First 5 names for display
                }
            })
        
        # Create a mock similarity if graph is empty
        if not self.graph:
            print("WARNING: No similarity data found in graph. Creating mock similarities for visualization.")
            # Create some mock edges for the largest families
            top_families = sorted(self.families, key=lambda f: f.count, reverse=True)[:10]
            for i, fam1 in enumerate(top_families):
                for j, fam2 in enumerate(top_families):
                    if i >= j:
                        continue
                    # Create mock similarity (70-99%)
                    mock_similarity = 70 + (i * j) % 30
                    edges.append({
                        'data': {
                            'source': fam1.id,
                            'target': fam2.id,
                            'weight': mock_similarity,
                            'label': f"{mock_similarity:.1f}% (mock)"
                        }
                    })
        else:
            # Create edges from the graph data
            edge_count = 0
            for family_id, similarities in self.graph.items():
                for other_id, similarity in similarities.items():
                    # Add edge if similarity exists
                    if similarity >= 0:
                        edges.append({
                            'data': {
                                'source': family_id,
                                'target': other_id,
                                'weight': similarity,
                                'label': f"{similarity:.1f}%"
                            }
                        })
                        edge_count += 1
            
            print(f"Created {edge_count} edges for network visualization")
        
        return nodes, edges
        
    def get_top_families(self, limit=10):
        """Get data for top families table"""
        if not self.families:
            return []
            
        # Sort families by size
        sorted_families = sorted(self.families, key=lambda f: f.count, reverse=True)
        top_families = sorted_families[:limit]
        
        # Format data for table
        table_data = []
        for i, family in enumerate(top_families):
            names = list(family.names)
            name_sample = ', '.join(names[:3])
            if len(names) > 3:
                name_sample += f"... (+{len(names)-3})"
                
            table_data.append({
                "Rank": i+1,
                "Size": family.count,
                "Names": len(names),
                "Example Names": name_sample,
                "Addresses": len(family.addresses)
            })
            
        return table_data

# Define CSS styles
custom_styles = {
    'stat_card': {
        'padding': '15px',
        'borderRadius': '5px',
        'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)',
        'backgroundColor': '#f8f8f8',
        'width': '22%',
        'textAlign': 'center'
    },
    'stat_card_title': {
        'margin': '0',
        'color': '#666',
        'fontSize': '16px'
    },
    'stat_card_value': {
        'margin': '10px 0 0 0',
        'color': '#333',
        'fontSize': '24px'
    },
    'row': {
        'margin': '20px 0',
        'padding': '15px',
        'borderRadius': '5px',
        'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)',
        'backgroundColor': 'white'
    }
}

# Initialize the Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server
app.title = "Contract Analysis Dashboard"

# Initialize the data processor
data_processor = ContractAnalysisDashboard()

# Define the app layout
app.layout = html.Div([
    html.H1("Contract Analysis Dashboard", style={"textAlign": "center"}),
    
    # Add auto-refresh interval component
    dcc.Interval(
        id='auto-refresh',
        interval=5000,  # in milliseconds (5 seconds)
        n_intervals=0
    ),
    
    # Data loading message
    html.Div(id="loading-message", children=[
        html.H3("Loading data...", style={"textAlign": "center", "color": "#888"})
    ]),
    
    # Main dashboard content (hidden until data loads)
    html.Div(id="dashboard-content", style={"display": "none"}, children=[
        # Network visualization MOVED TO TOP
        html.Div(className="row", style=custom_styles['row'], children=[
            html.H3("Contract Family Network"),
            html.Div(style={"display": "flex", "justifyContent": "space-between", "marginBottom": "10px"}, children=[
                html.Div(style={"display": "flex", "alignItems": "center"}, children=[
                    html.Label("Layout:", style={"marginRight": "10px"}),
                    dcc.Dropdown(
                        id="cytoscape-layout",
                        options=[
                            {"label": "Concentric", "value": "concentric"},
                            {"label": "Breadthfirst", "value": "breadthfirst"},
                            {"label": "Circle", "value": "circle"},
                            {"label": "Grid", "value": "grid"},
                            {"label": "Force-directed", "value": "cose"}
                        ],
                        value="concentric",
                        style={"width": "200px"}
                    )
                ]),
                html.Div(style={"display": "flex", "alignItems": "center"}, children=[
                    html.Label("Node Spacing:", style={"marginRight": "10px"}),
                    html.Div(style={"width": "300px"}, children=[
                        dcc.Slider(
                            id="node-spacing-slider",
                            min=50,
                            max=200,
                            step=10,
                            value=100,
                            marks={50: '50%', 100: '100%', 150: '150%', 200: '200%'},
                            tooltip={"placement": "bottom", "always_visible": True}
                        )
                    ])
                ]),
                html.Div(style={"display": "flex", "alignItems": "center"}, children=[
                    dcc.Checklist(
                        id="family-size-filter",
                        options=[
                            {"label": "Show only multi-contract families", "value": "filter"}
                        ],
                        value=["filter"],  # Default to checked
                        style={"marginRight": "10px"}
                    )
                ])
            ]),
            cyto.Cytoscape(
                id="family-network",
                layout={"name": "concentric", "animate": True, "spacingFactor": 1.0},
                style={"width": "100%", "height": "600px", "border": "1px solid #ccc"},
                elements=[],
                stylesheet=[
                    # Node styling
                    {
                        "selector": "node",
                        "style": {
                            "width": "data(size)",
                            "height": "data(size)",
                            "content": "data(label)",
                            "font-size": "12px",
                            "text-valign": "center",
                            "text-halign": "center",
                            "background-color": "#6FB1FC",
                            "text-outline-width": 1,
                            "text-outline-color": "#fff",
                            "color": "#333"
                        }
                    },
                    # Edge styling
                    {
                        "selector": "edge",
                        "style": {
                            "line-color": "#ccc",
                            "width": 2,
                            "curve-style": "bezier",
                            "label": "data(label)",
                            "font-size": "10px",
                            "text-background-color": "#fff",
                            "text-background-opacity": 1,
                            "text-background-padding": "2px"
                        }
                    },
                    # Selected node styling
                    {
                        "selector": ":selected",
                        "style": {
                            "background-color": "#FF5733",
                            "line-color": "#FF5733",
                            "border-width": 2,
                            "border-color": "#333"
                        }
                    }
                ]
            ),
            # Node details panel
            html.Div(id="node-details", style={"margin": "15px 0", "padding": "10px", "border": "1px solid #ddd"})
        ]),
        
        # Summary stats cards
        html.Div(className="stats-container", children=[
            html.Div(className="stat-card", style=custom_styles['stat_card'], children=[
                html.H3("Total Families", style=custom_styles['stat_card_title']),
                html.H2(id="total-families", style=custom_styles['stat_card_value'])
            ]),
            html.Div(className="stat-card", style=custom_styles['stat_card'], children=[
                html.H3("Total Contracts", style=custom_styles['stat_card_title']),
                html.H2(id="total-contracts", style=custom_styles['stat_card_value'])
            ]),
            html.Div(className="stat-card", style=custom_styles['stat_card'], children=[
                html.H3("Unique Names", style=custom_styles['stat_card_title']),
                html.H2(id="unique-names", style=custom_styles['stat_card_value'])
            ]),
            html.Div(className="stat-card", style=custom_styles['stat_card'], children=[
                html.H3("Avg. Contracts/Family", style=custom_styles['stat_card_title']),
                html.H2(id="avg-contracts", style=custom_styles['stat_card_value'])
            ])
        ], style={"display": "flex", "justifyContent": "space-between", "margin": "20px 0"}),
        
        # First row of visualizations
        html.Div(className="row", style=custom_styles['row'], children=[
            # Family size distribution
            html.Div(className="six columns", children=[
                html.H3("Family Size Distribution"),
                dcc.Graph(id="family-size-chart")
            ]),
            
            # Top contract names
            html.Div(className="six columns", children=[
                html.H3("Top Contract Names"),
                dcc.Graph(id="name-frequency-chart")
            ])
        ]),
        
        # Top families table
        html.Div(className="row", style=custom_styles['row'], children=[
            html.H3("Top Contract Families"),
            dash_table.DataTable(
                id="top-families-table",
                columns=[
                    {"name": "Rank", "id": "Rank"},
                    {"name": "Size", "id": "Size"},
                    {"name": "Unique Names", "id": "Names"},
                    {"name": "Example Names", "id": "Example Names"},
                    {"name": "Addresses", "id": "Addresses"}
                ],
                style_table={"overflowX": "auto"},
                style_cell={
                    "textAlign": "left",
                    "padding": "5px",
                    "whiteSpace": "normal",
                    "height": "auto"
                },
                style_header={
                    "backgroundColor": "#f2f2f2",
                    "fontWeight": "bold"
                },
                style_data_conditional=[
                    {
                        "if": {"row_index": "odd"},
                        "backgroundColor": "#f9f9f9"
                    }
                ]
            )
        ])
    ])
])

# Define callbacks
@app.callback(
    [Output("dashboard-content", "style"),
     Output("loading-message", "style"),
     Output("total-families", "children"),
     Output("total-contracts", "children"),
     Output("unique-names", "children"),
     Output("avg-contracts", "children"),
     Output("family-size-chart", "figure"),
     Output("name-frequency-chart", "figure"),
     Output("top-families-table", "data"),
     Output("family-network", "elements")],
    [Input("dashboard-content", "id"),
     Input("auto-refresh", "n_intervals"),
     Input("family-size-filter", "value")]  # Add the filter input
)
def load_dashboard_data(_, n_intervals, size_filter):
    """Load data and update initial dashboard components"""
    # Load the data
    success = data_processor.load_data()
    
    if not success:
        # Keep loading message visible and hide dashboard
        return {"display": "none"}, {"display": "block"}, "", "", "", "", {}, {}, [], []
    
    # Get basic stats
    stats = data_processor.get_basic_stats()
    
    # Create family size chart
    sizes, counts = data_processor.get_family_size_data()
    size_fig = px.bar(
        x=sizes, y=counts, 
        labels={"x": "Family Size (Number of Contracts)", "y": "Number of Families"},
        title="Distribution of Contract Family Sizes"
    )
    size_fig.update_layout(
        xaxis=dict(tickmode='linear'),
        showlegend=False
    )
    
    # Create name frequency chart
    name_data = data_processor.get_name_frequency_data()
    name_fig = px.bar(
        x=[name for name, _ in name_data], 
        y=[count for _, count in name_data],
        labels={"x": "Contract Name", "y": "Frequency"},
        title="Top Contract Names"
    )
    name_fig.update_layout(
        xaxis={'categoryorder':'total descending'},
        showlegend=False
    )
    
    # Get top families data
    top_families = data_processor.get_top_families()
    
    # Get network data with size filter
    filter_active = size_filter and "filter" in size_filter
    nodes, edges = get_filtered_network_data(filter_active)
    
    # Show dashboard and hide loading message
    return (
        {"display": "block"}, 
        {"display": "none"}, 
        stats["total_families"],
        stats["total_contracts"],
        stats["unique_names"],
        f"{stats['avg_contracts_per_family']:.1f}",
        size_fig,
        name_fig,
        top_families,
        nodes + edges  # Combine nodes and edges for the network
    )

def get_filtered_network_data(filter_active):
    """Get network data with optional filtering for family size > 1"""
    families = data_processor.families
    
    # Apply filtering if needed
    if filter_active:
        # Only include families with more than one contract
        families = [family for family in families if family.count > 1]
    
    nodes = []
    edges = []
    
    # Create nodes for each family (using family ID as the node ID)
    for family in families:
        # Get a representative name for the family
        names = list(family.names)
        if names:
            name = names[0]
            if len(name) > 15:
                name = name[:12] + "..."
        else:
            name = f"Family {family.id[:8]}"
            
        # Determine node size based on contract count
        size = max(20, min(100, 20 + family.count * 5))
        
        # Create node
        nodes.append({
            'data': {
                'id': family.id,
                'label': name,
                'size': size,
                'contract_count': family.count,
                'name_count': len(family.names),
                'addresses': len(family.addresses),
                'names': list(family.names)[:5],  # First 5 names for display
            }
        })
    
    # Create family ID map for filtered families
    filtered_family_ids = {family.id for family in families}
    
    # Create a mock similarity if graph is empty
    graph = data_processor.graph
    if not graph:
        print("WARNING: No similarity data found in graph. Creating mock similarities for visualization.")
        # Create some mock edges for the largest families
        top_families = sorted(families, key=lambda f: f.count, reverse=True)[:10]
        for i, fam1 in enumerate(top_families):
            for j, fam2 in enumerate(top_families):
                if i >= j:
                    continue
                # Create mock similarity (70-99%)
                mock_similarity = 70 + (i * j) % 30
                edges.append({
                    'data': {
                        'source': fam1.id,
                        'target': fam2.id,
                        'weight': mock_similarity,
                        'label': f"{mock_similarity:.1f}% (mock)"
                    }
                })
    else:
        # Create edges from the graph data, only for filtered families
        edge_count = 0
        for family_id, similarities in graph.items():
            # Skip if source family is filtered out
            if family_id not in filtered_family_ids:
                continue
                
            for other_id, similarity in similarities.items():
                # Skip if target family is filtered out
                if other_id not in filtered_family_ids:
                    continue
                    
                # Add edge if similarity exists
                if similarity >= 0:
                    edges.append({
                        'data': {
                            'source': family_id,
                            'target': other_id,
                            'weight': similarity,
                            'label': f"{similarity:.1f}%"
                        }
                    })
                    edge_count += 1
        
        print(f"Created {edge_count} edges for network visualization")
    
    return nodes, edges

@app.callback(
    Output("family-network", "layout"),
    [Input("cytoscape-layout", "value"),
     Input("node-spacing-slider", "value")]
)
def update_network_layout(layout, spacing):
    """Update the network layout"""
    # Convert spacing slider value to a spacing factor (50-200% → 0.5-2.0)
    spacing_factor = spacing / 100
    
    return {
        "name": layout, 
        "animate": True,
        "spacingFactor": spacing_factor
    }

@app.callback(
    Output("node-details", "children"),
    [Input("family-network", "selectedNodeData")]
)
def display_node_details(node_data):
    """Display details about the selected node (family)"""
    if not node_data:
        return html.P("Click on a node to see family details")
        
    node = node_data[0]
    return html.Div([
        html.H4(f"Family: {node['label']}"),
        html.Div([
            html.P(f"Contracts: {node['contract_count']}"),
            html.P(f"Unique Names: {node['name_count']}"),
            html.P(f"Contract Addresses: {node['addresses']}"),
            html.H5("Example Names:"),
            html.Ul([html.Li(name) for name in node['names']])
        ])
    ])

# Run the app
if __name__ == "__main__":
    print("=== Contract Analysis Dashboard ===")
    print("Starting Dash server...")
    app.run(debug=True)