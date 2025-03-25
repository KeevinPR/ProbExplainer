import dash
from dash import dcc, html, Input, Output, State, ALL
import dash_bootstrap_components as dbc
import base64
import io
import json
import logging
import warnings
from dash.exceptions import PreventUpdate

# Example: using pgmpy to read a .bif and display nodes/states (for demonstration purposes)
from pgmpy.readwrite import BIFReader

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------- (1) CREATE DASH APP ---------- #
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    requests_pathname_prefix='/Evidence/ProbExplainerDash/',
    suppress_callback_exceptions=True
)

server = app.server

# ---------- (2) LOAD DEFAULT BAYESIAN NETWORK (network_5.bif) WITH PGMPY ---------- #
# Note: You can replace 'network_5.bif' with the path to your default network if desired.
reader = BIFReader('/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/ProbExplainer/expert_networks/network_5.bif')
default_model_pgmpy = reader.get_model()

# ---------- (3) APP LAYOUT ---------- #
app.layout = html.Div([
    dcc.Loading(
        id="global-spinner",
        overlay_style={"visibility":"visible", "filter": "blur(1px)"},
        type="circle",        # You can choose "circle", "dot", "default", etc.
        fullscreen=False,      # This ensures it covers the entire page
        children=html.Div([
        html.H1("Bayesian Network ProbExplainer ", style={'textAlign': 'center'}),

        # Section to upload .bif file or use default network
        html.Div([
            html.H3("Upload a .bif File or Use Default Network (network_5.bif)", style={'textAlign': 'center'}),
            dcc.Upload(
                id='upload-bif',
                children=html.Button('Upload .bif File'),
                style={'textAlign': 'center'}
            ),
            html.Br(),
            dcc.Checklist(
                id='use-default-network',
                options=[{'label': ' Use Default Network (network_5.bif)', 'value': 'default'}],
                value=['default'],  # By default uses 'network_5.bif'
                style={'textAlign': 'center'}
            ),
        ], style={'textAlign': 'center'}),

        html.Hr(),

        # Section to select action
        html.Div([
            html.H3("Select an Action to Perform", style={'textAlign': 'center'}),
            dcc.Dropdown(
                id='action-dropdown',
                options=[
                    {'label': 'Compute Posterior', 'value': 'posterior'},
                    {'label': 'Map Independence', 'value': 'map_independence'},
                    # Changed label from "Get Defeaters (Not Implemented)" to "Get Defeaters"
                    {'label': 'Get Defeaters', 'value': 'defeaters'}
                ],
                value='posterior',  # Default action
                style={'width': '50%', 'margin': '0 auto'}
            )
        ]),

        html.Hr(),

        # Evidence selection
        html.Div([
            html.H3("Select Evidence Variables", style={'textAlign': 'center'}),
            dcc.Dropdown(
                id='evidence-vars-dropdown',
                options=[{'label': var, 'value': var} for var in default_model_pgmpy.nodes()],
                multi=True,
                placeholder="Select evidence variables",
                style={'width': '50%', 'margin': '0 auto'}
            ),
            html.Div(id='evidence-values-container')
        ], style={'marginBottom': '20px'}),

        html.Hr(),

        # Target variables
        html.Div([
            html.H3("Select Target Variables", style={'textAlign': 'center'}),
            dcc.Dropdown(
                id='target-vars-dropdown',
                options=[],  # Will be dynamically updated
                multi=True,
                placeholder="Select target variables",
                style={'width': '50%', 'margin': '0 auto'}
            )
        ], style={'marginBottom': '20px'}),

        html.Hr(),

        # Set R (only needed for map_independence)
        html.Div([
            html.H3("Select Set R (only for Map Independence)", style={'textAlign': 'center'}),
            dcc.Dropdown(
                id='r-vars-dropdown',
                options=[],
                multi=True,
                placeholder="Select R variables",
                style={'width': '50%', 'margin': '0 auto'}
            )
        ], style={'marginBottom': '20px'}),

        html.Hr(),

        # Run button
        html.Div([
            html.Button('Run', id='run-action-button', n_clicks=0)
        ], style={'textAlign': 'center'}),
        html.Br(),
        html.Div(id='action-results', style={'textAlign': 'center'}),

        # dcc.Store to keep the chosen network
        dcc.Store(id='stored-network'),
    ])
    ) # end of dcc.Loading
])

# ---------- (4) CALLBACKS ---------- #

############################################
# Store the chosen network (default or uploaded)
############################################
@app.callback(
    Output('stored-network', 'data'),
    Input('upload-bif', 'contents'),
    State('upload-bif', 'filename'),
    Input('use-default-network', 'value')
)
def load_network(contents, filename, use_default_value):
    """
    Internally store (in 'stored-network') the BN content.
    - If 'default' is selected or no file is uploaded, load the default network (network_5.bif).
    - If a .bif is uploaded, read and store it as a string.
    """
    if 'default' in use_default_value or contents is None:
        logger.info("Using default network: network_5.bif")
        return {
            'network_name': 'network_5.bif',
            'network_type': 'path',
            'content': '/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/ProbExplainer/expert_networks/network_5.bif'
        }
    else:
        logger.info(f"Attempting to load uploaded network: {filename}")
        # Decode
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            bif_data = decoded.decode('utf-8')
            # Use pgmpy to verify it's a valid network
            reader_check = BIFReader(string=bif_data)
            _ = reader_check.get_model()  # if this fails, an error is raised
            logger.info(f"Valid network: {filename}")
            return {
                'network_name': filename,
                'network_type': 'string',
                'content': bif_data
            }
        except Exception as e:
            logger.error(f"Error loading network: {e}")
            return dash.no_update

############################################
# Update target and R variable options,
# excluding those already chosen as evidence
############################################
@app.callback(
    Output('target-vars-dropdown', 'options'),
    Output('r-vars-dropdown', 'options'),
    Input('evidence-vars-dropdown', 'value'),
    State('stored-network', 'data')
)
def update_target_r_options(evidence_vars, stored_network):
    if stored_network is None:
        return [], []
    try:
        # Load the network with pgmpy just to get the list of nodes
        if stored_network['network_type'] == 'path':
            reader_local = BIFReader(stored_network['content'])
            net = reader_local.get_model()
            all_vars = net.nodes()
        else:  # 'string'
            reader_local = BIFReader(string=stored_network['content'])
            net = reader_local.get_model()
            all_vars = net.nodes()

        ev_vars = set(evidence_vars) if evidence_vars else set()
        valid_vars = [v for v in all_vars if v not in ev_vars]

        opts = [{'label': v, 'value': v} for v in sorted(valid_vars)]
        return opts, opts
    except Exception as e:
        logger.error(f"Error updating target/R: {e}")
        return [], []

############################################
# Generate dropdowns for evidence values
############################################
@app.callback(
    Output('evidence-values-container', 'children'),
    Input('evidence-vars-dropdown', 'value'),
    State('stored-network', 'data')
)
def update_evidence_values(evidence_vars, stored_network):
    if not evidence_vars:
        return []
    if stored_network is None:
        return []

    # We display the possible states for each selected evidence variable
    # using pgmpy (just to build the UI). Later, PyAgrum will do the actual inference.
    children = []
    try:
        if stored_network['network_type'] == 'path':
            reader_local = BIFReader(stored_network['content'])
            net = reader_local.get_model()
        else:  # 'string'
            reader_local = BIFReader(string=stored_network['content'])
            net = reader_local.get_model()

        for var in evidence_vars:
            var_states = net.get_cpds(var).state_names[var]
            children.append(
                html.Div(
                    [
                        html.Label(f"Value for {var}: ", style={'marginRight': '10px'}),
                        dcc.Dropdown(
                            id={'type': 'evidence-value-dropdown', 'index': var},
                            options=[{'label': s, 'value': s} for s in var_states],
                            value=var_states[0] if var_states else None,
                            style={'width': '200px'}
                        )
                    ],
                    style={'textAlign': 'center', 'marginBottom': '10px'}
                )
            )
        return children
    except Exception as e:
        logger.error(f"Error in update_evidence_values: {e}")
        return []

############################################
# Main callback to execute the selected action
############################################
@app.callback(
    Output('action-results', 'children'),
    Input('run-action-button', 'n_clicks'),
    State('action-dropdown', 'value'),
    State('stored-network', 'data'),
    State('evidence-vars-dropdown', 'value'),
    State({'type': 'evidence-value-dropdown', 'index': ALL}, 'value'),
    State({'type': 'evidence-value-dropdown', 'index': ALL}, 'id'),
    State('target-vars-dropdown', 'value'),
    State('r-vars-dropdown', 'value')
)
def run_action(n_clicks, action, stored_network,
               evidence_vars, evidence_values, evidence_ids,
               target_vars, r_vars):
    if n_clicks is None or n_clicks == 0:
        raise PreventUpdate

    if not stored_network:
        return html.Div("Please upload a .bif file or use the default network.", style={'color': 'red'})

    # Build the evidence dictionary
    evidence_dict = {}
    if evidence_vars and evidence_values and evidence_ids:
        for ev_id, val in zip(evidence_ids, evidence_values):
            var = ev_id['index']
            evidence_dict[var] = val

    # --- 1) Create a PyAgrum instance via BayesianNetworkPyAgrum (ProbExplainer) --- #
    import pyAgrum as gum
    from probExplainer.model.BayesianNetwork import BayesianNetworkPyAgrum, ImplausibleEvidenceException

    # Load the network into pyAgrum
    bn_pya = None
    try:
        if stored_network['network_type'] == 'path':
            bn_pya = gum.loadBN(stored_network['content'])
        else:
            bn_pya = gum.loadBNFromString(stored_network['content'])
    except Exception as e:
        return html.Div(f"Error loading the network in pyAgrum: {e}", style={'color': 'red'})

    # Instantiate the ProbExplainer adapter
    try:
        bn_adapter = BayesianNetworkPyAgrum(bn_pya)
    except Exception as e:
        return html.Div(f"Error creating BayesianNetworkPyAgrum: {e}", style={'color': 'red'})

    # --- 2) Perform the chosen action --- #
    if action == 'posterior':
        # Requires evidence_vars and target_vars
        if not target_vars:
            return html.Div("Please select at least one target variable for Compute Posterior.", style={'color': 'red'})
        try:
            posterior_array = bn_adapter.compute_posterior(evidence_dict, target_vars)
            domain = bn_adapter.get_domain_of(target_vars)
            probs_list = posterior_array.flatten().tolist()

            results_str = []
            for i, states in enumerate(domain):
                results_str.append(f"{states} -> {probs_list[i]:.6f}")
            return html.Pre("Compute Posterior\n" + "\n".join(results_str))

        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in compute_posterior: {e}", style={'color': 'red'})

    elif action == 'map_independence':
        # Requires evidence, target_vars, and set R
        if not target_vars:
            return html.Div("Please select at least one target variable for Map Independence.", style={'color': 'red'})
        if not r_vars:
            return html.Div("Please select at least one variable in R for Map Independence.", style={'color': 'red'})

        try:
            map_result = bn_adapter.maximum_a_posteriori(evidence_dict, target_vars)
            map_dict, map_prob = map_result[0], map_result[1]
            independence_bool = bn_adapter.map_independence(r_vars, evidence_dict, map_dict)

            if independence_bool:
                return html.Div(
                    f"The MAP assignment {map_dict} is NOT altered by interventions on {r_vars} (INDEPENDENT).",
                    style={'color': 'green'}
                )
            else:
                return html.Div(
                    f"The MAP assignment {map_dict} IS altered by {r_vars} (DEPENDENT).",
                    style={'color': 'blue'}
                )
        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in map_independence: {e}", style={'color': 'red'})

    elif action == 'defeaters':
        # *** Implemented now ***
        if not target_vars:
            return html.Div("Please select at least one target variable for Get Defeaters.", style={'color': 'red'})

        # Import your get_defeaters function
        from probExplainer.algorithms.defeater import get_defeaters

        try:
            # Hardcoded defaults: depth=∞, evaluate_singletons=True
            relevant_sets, irrelevant_sets = get_defeaters(
                model=bn_adapter,
                evidence=evidence_dict,
                target=target_vars,
                depth=float('inf'),
                evaluate_singletons=True
            )

            # Format results
            if not relevant_sets:
                relevant_str = "None"
            else:
                relevant_str = "\n".join(map(str, relevant_sets))
            if not irrelevant_sets:
                irrelevant_str = "None"
            else:
                irrelevant_str = "\n".join(map(str, irrelevant_sets))

            return html.Div([
                html.H4("Get Defeaters Results"),
                html.P("Relevant sets (these can alter the MAP assignment):"),
                html.Pre(relevant_str),
                html.P("Irrelevant sets (cannot alter MAP):"),
                html.Pre(irrelevant_str)
            ], style={'whiteSpace':'pre-wrap'})

        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in get_defeaters: {e}", style={'color': 'red'})

    else:
        return html.Div("Unknown action.", style={'color': 'red'})


# ---------- (5) RUN THE SERVER ---------- #
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8054)
