import dash
from dash import dcc, html, Input, Output, State, ALL
import dash_bootstrap_components as dbc
import base64
import json
import logging
import warnings
from dash.exceptions import PreventUpdate

from pgmpy.readwrite import BIFReader

import pyAgrum as gum
import os
import tempfile

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


# ---------- (2) HELPER FUNCTION FOR pyAgrum PARSING FROM STRING ---------- #
def loadBNfromMemory(bif_string):
    """
    Workaround for pyAgrum versions that do NOT have loadBNFromString.
    We write 'bif_string' into a temp .bif file, then load it.
    """
    with tempfile.NamedTemporaryFile(suffix=".bif", delete=False, mode='w') as tmp:
        tmp_name = tmp.name
        tmp.write(bif_string)
    try:
        bn = gum.loadBN(tmp_name)
    finally:
        # Clean up the temp file
        os.remove(tmp_name)
    return bn


# ---------- (3) APP LAYOUT ---------- #
app.layout = html.Div([
    dcc.Loading(
        id="global-spinner",
        overlay_style={"visibility": "visible", "filter": "blur(1px)"},
        type="circle",
        fullscreen=False,
        children=html.Div([
            html.H1("Bayesian Network ProbExplainer ", style={'textAlign': 'center'}),

            ########################################################
            # Info text
            ########################################################
            html.Div(
                className="link-bar",
                style={
                    "textAlign": "center",
                    "marginBottom": "20px"
                },
                children=[
                    html.A(
                        children=[
                            html.Img(
                                src="https://cig.fi.upm.es/wp-content/uploads/github.png",
                                style={"height": "24px", "marginRight": "8px"}
                            ),
                            "Original GitHub"
                        ],
                        href="https://github.com/Enrique-Val/ProbExplainer",
                        target="_blank",
                        className="btn btn-outline-info me-2"
                    ),
                    html.A(
                        children=[
                            html.Img(
                                src="https://cig.fi.upm.es/wp-content/uploads/2023/11/cropped-logo_CIG.png",
                                style={"height": "24px", "marginRight": "8px"}
                            ),
                            "Paper PDF"
                        ],
                        href="https://cig.fi.upm.es/wp-content/uploads/2024/01/Efficient-search-for-relevance-explanations-using-MAP-independence-in-Bayesian-networks.pdf",
                        target="_blank",
                        className="btn btn-outline-primary me-2"
                    ),
                    html.A(
                        children=[
                            html.Img(
                                src="https://cig.fi.upm.es/wp-content/uploads/github.png",
                                style={"height": "24px", "marginRight": "8px"}
                            ),
                            "Dash Adapted GitHub"
                        ],
                        href="https://github.com/KeevinPR/ProbExplainer",
                        target="_blank",
                        className="btn btn-outline-info me-2"
                    ),
                ]
            ),
            ########################################################
            # Short explanatory text
            ########################################################
            html.Div(
                [
                    html.P(
                        "Library to adapt and explain probabilistic models and specially aimed for Bayesian networks.",
                        style={"textAlign": "center", "maxWidth": "800px", "margin": "0 auto"}
                    )
                ],
                style={"marginBottom": "20px"}
            ),

            ########################################################
            # (A) Data upload
            ########################################################
            html.Div(className="card", children=[
                html.H3("1. Upload Dataset", style={'textAlign': 'center'}),

                # Container "card"
                html.Div([
                    # Top part with icon and text
                    html.Div([
                        html.Img(
                            src="https://img.icons8.com/ios-glyphs/40/cloud--v1.png",
                            className="upload-icon"
                        ),
                        html.Div("Drag and drop or select a CSV/BIF file", className="upload-text")
                    ]),
                    
                    # Upload component
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([], style={'display': 'none'}),
                        className="upload-dropzone",
                        multiple=False
                    ),
                ], className="upload-card"),

                # Use default dataset + help icon
                html.Div([
                    dcc.Checklist(
                        id='use-default-network',
                        options=[{'label': 'Use the default dataset', 'value': 'default'}],
                        value=[],
                        style={'display': 'inline-block', 'textAlign': 'center', 'marginTop': '10px'}
                    ),
                    dbc.Button(
                        html.I(className="fa fa-question-circle"),
                        id="help-button-default-dataset",
                        color="link",
                        style={"display": "inline-block", "marginLeft": "8px"}
                    ),
                ], style={'textAlign': 'center'}),
            ]),

            # Section to select action
            html.Div(className="card", children=[
                html.H3("Select an Action to Perform", style={'textAlign': 'center'}),
                dcc.Dropdown(
                    id='action-dropdown',
                    options=[
                        {'label': 'Compute Posterior', 'value': 'posterior'},
                        {'label': 'Map Independence', 'value': 'map_independence'},
                        {'label': 'Get Defeaters', 'value': 'defeaters'}
                    ],
                    value='posterior',  # Default action
                    style={'width': '50%', 'margin': '0 auto'}
                )
            ]),

            # Evidence selection
            html.Div(className="card", children=[
                html.H3("Select Evidence Variables", style={'textAlign': 'center'}),
                dcc.Dropdown(
                    id='evidence-vars-dropdown',
                    options=[],  # now empty until network loaded
                    multi=True,
                    placeholder="Select evidence variables",
                    style={'width': '50%', 'margin': '0 auto'}
                ),
                html.Div(id='evidence-values-container')
            ], style={'marginBottom': '20px'}),

            # Target variables
            html.Div(className="card", children=[
                html.H3("Select Target Variables", style={'textAlign': 'center'}),
                dcc.Dropdown(
                    id='target-vars-dropdown',
                    options=[],  # dynamically updated
                    multi=True,
                    placeholder="Select target variables",
                    style={'width': '50%', 'margin': '0 auto'}
                )
            ], style={'marginBottom': '20px'}),

            # Set R (only needed for map_independence)
            html.Div(className="card", children=[
                html.H3("Select Set R (only for Map Independence)", style={'textAlign': 'center'}),
                dcc.Dropdown(
                    id='r-vars-dropdown',
                    options=[],
                    multi=True,
                    placeholder="Select R variables",
                    style={'width': '50%', 'margin': '0 auto'}
                )
            ], style={'marginBottom': '20px'}),

            # Run button
            html.Div([
                html.Button('Run', id='run-action-button', n_clicks=0)
            ], style={'textAlign': 'center'}),
            html.Br(),
            html.Div(id='action-results', style={'textAlign': 'center'}),

            # Store to keep the chosen network path/string
            dcc.Store(id='stored-network'),

            # Store to keep the nodes and states (so we don't parse repeatedly)
            dcc.Store(id='stored-model-info'),
        ])
    )
])


# ---------- (4) CALLBACKS ---------- #

# (A) Checking the "Use default" => set 'upload-data.contents'
@app.callback(
    Output('upload-data', 'contents'),
    Input('use-default-network', 'value'),
    prevent_initial_call=True
)
def use_default_dataset(value):
    """
    If 'default' is checked, read your local 'carwithnames.data' (or a default .bif) file,
    encode as base64, set upload-data.contents, triggering parse callback.
    
    NOTE: If 'carwithnames.data' is NOT a BIF, parsing will fail.
    """
    if 'default' in value:
        default_file = '/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/Counterfactuals/carwithnames.data'
        try:
            with open(default_file, 'rb') as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode()
            return f"data:text/csv;base64,{b64}"
        except Exception as e:
            print(f"Error reading default dataset: {e}")
            return dash.no_update
    return dash.no_update


# (B) Store the chosen network (default or uploaded) in 'stored-network'
@app.callback(
    Output('stored-network', 'data'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    Input('use-default-network', 'value')
)
def load_network(contents, filename, default_value):
    """
    Store path/string in 'stored-network'.
    
    - If 'default' is in default_value => use the known path to network_5.bif (or your default).
    - If user uploads => decode the BIF string.
    - If nothing => PreventUpdate.
    """
    # If neither default is checked nor any file is uploaded => do nothing
    if (not contents) and ('default' not in default_value):
        raise PreventUpdate

    # If "Use default" is checked => always override with that
    if 'default' in default_value:
        logger.info("Using default network: network_5.bif")
        return {
            'network_name': 'network_5.bif',
            'network_type': 'path',
            # Adjust path to your real default BIF
            'content': '/var/www/html/CIGModels/backend/cigmodelsdjango/cigmodelsdjangoapp/ProbExplainer/expert_networks/network_5.bif'
        }

    # Otherwise, if user uploaded something:
    if contents:
        logger.info(f"Attempting to load uploaded network: {filename}")
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            bif_data = decoded.decode('utf-8')
            # Check if valid BIF with pgmpy
            reader_check = BIFReader(string=bif_data)
            _ = reader_check.get_model()  # fails if invalid
            logger.info(f"Valid network uploaded: {filename}")
            return {
                'network_name': filename,
                'network_type': 'string',
                'content': bif_data
            }
        except Exception as e:
            logger.error(f"Error loading network: {e}")
            return dash.no_update

    raise PreventUpdate


# (C) Once 'stored-network' is set, parse it with pgmpy => store nodes/states in 'stored-model-info'
@app.callback(
    Output('stored-model-info', 'data'),
    Input('stored-network', 'data')
)
def parse_network_and_store_info(stored_net):
    if not stored_net:
        raise PreventUpdate

    logger.info("Parsing network with pgmpy to extract nodes/states...")
    try:
        if stored_net['network_type'] == 'path':
            reader_local = BIFReader(stored_net['content'])
        else:
            # read from string
            reader_local = BIFReader(string=stored_net['content'])

        net = reader_local.get_model()
        nodes_list = sorted(net.nodes())

        # For each node, gather possible states:
        states_dict = {}
        for var in nodes_list:
            cpd = net.get_cpds(var)
            states_dict[var] = cpd.state_names[var]

        return {
            'nodes': nodes_list,
            'states': states_dict
        }
    except Exception as e:
        logger.error(f"Error parsing network in parse_network_and_store_info: {e}")
        return dash.no_update


# (D) Update Evidence/Target/R options from the stored model info
@app.callback(
    Output('evidence-vars-dropdown', 'options'),
    Output('target-vars-dropdown', 'options'),
    Output('r-vars-dropdown', 'options'),
    Input('stored-model-info', 'data')
)
def update_dropdown_options(model_info):
    if not model_info:
        return [], [], []
    nodes_list = model_info['nodes']
    opts = [{'label': var, 'value': var} for var in nodes_list]
    return opts, opts, opts


# (E) Generate the evidence-value dropdowns
@app.callback(
    Output('evidence-values-container', 'children'),
    Input('evidence-vars-dropdown', 'value'),
    State('stored-model-info', 'data')
)
def update_evidence_values(evidence_vars, model_info):
    if not evidence_vars or not model_info:
        return []

    states_dict = model_info['states']  # var -> list_of_states
    children = []
    for var in evidence_vars:
        var_states = states_dict.get(var, [])
        children.append(
            html.Div(
                [
                    html.Label(f"Value for {var}: ", style={'marginRight': '10px'}),
                    dcc.Dropdown(
                        id={'type': 'evidence-value-dropdown', 'index': var},
                        options=[{'label': s, 'value': s} for s in var_states],
                        style={'width': '200px'}
                    )
                ],
                style={'textAlign': 'center', 'marginBottom': '10px'}
            )
        )
    return children


# (F) OPTIONAL: If you want to exclude chosen evidence from target/R
@app.callback(
    Output('target-vars-dropdown', 'options', allow_duplicate=True),
    Output('r-vars-dropdown', 'options', allow_duplicate=True),
    Input('evidence-vars-dropdown', 'value'),
    State('stored-model-info', 'data'),
    prevent_initial_call=True
)
def exclude_evidence_from_target_r(evidence_vars, model_info):
    if not model_info:
        raise PreventUpdate

    all_nodes = model_info['nodes']
    if not evidence_vars:
        # If no evidence chosen, all nodes valid
        opts = [{'label': n, 'value': n} for n in all_nodes]
        return opts, opts

    ev_set = set(evidence_vars)
    filtered = [n for n in all_nodes if n not in ev_set]
    opts = [{'label': n, 'value': n} for n in filtered]
    return opts, opts


# (G) Main callback: run the chosen action
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
    if not n_clicks:
        raise PreventUpdate

    if not stored_network:
        return html.Div("No network loaded. Please upload or select the default network.", style={'color': 'red'})

    # Build evidence dict
    evidence_dict = {}
    if evidence_vars and evidence_values and evidence_ids:
        for ev_id, val in zip(evidence_ids, evidence_values):
            if val is not None:  # ignore if none
                var = ev_id['index']
                evidence_dict[var] = val

    from probExplainer.model.BayesianNetwork import BayesianNetworkPyAgrum, ImplausibleEvidenceException

    # Load BN with pyAgrum (without loadBNFromString)
    try:
        if stored_network['network_type'] == 'path':
            bn_pya = gum.loadBN(stored_network['content'])
        else:
            # if it's a string => use our helper
            bn_pya = loadBNfromMemory(stored_network['content'])
    except Exception as e:
        return html.Div(f"Error loading network in pyAgrum: {e}", style={'color': 'red'})

    try:
        bn_adapter = BayesianNetworkPyAgrum(bn_pya)
    except Exception as e:
        return html.Div(f"Error creating BayesianNetworkPyAgrum: {e}", style={'color': 'red'})

    # Perform chosen action
    if action == 'posterior':
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
        if not target_vars:
            return html.Div("Please select at least one target variable for Get Defeaters.", style={'color': 'red'})

        from probExplainer.algorithms.defeater import get_defeaters
        try:
            relevant_sets, irrelevant_sets = get_defeaters(
                model=bn_adapter,
                evidence=evidence_dict,
                target=target_vars,
                depth=float('inf'),
                evaluate_singletons=True
            )
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
            ], style={'whiteSpace': 'pre-wrap'})

        except ImplausibleEvidenceException:
            return html.Div("Impossible Evidence (ImplausibleEvidenceException).", style={'color': 'red'})
        except Exception as e:
            return html.Div(f"Error in get_defeaters: {e}", style={'color': 'red'})

    else:
        return html.Div("Unknown action.", style={'color': 'red'})


# ---------- (5) RUN THE SERVER ---------- #
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8054)