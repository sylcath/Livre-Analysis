%% Import data from spreadsheet
clear
close all

opts = spreadsheetImportOptions("NumVariables", 36);
opts.Sheet = "Fig A2.11";
opts.DataRange = "C10:AL11";
opts.VariableNames = "Var" + string(3:38);
opts.VariableTypes = repmat("double", 1, 36);

T = readtable("C:\Users\Windows\Dropbox\Livre\Data\econ-gen-pib-composante(2) (version 1).xlsx", opts, "UseExcel", false);

% 35x2 (rows = cohorts, cols = series)
Y = table2array(T).';  % transpose so cohorts run down rows
Year = (1940:(1940+size(Y,1)-1)).';
%% Figure (clean, B/W, unified font size ×1.5, TeX xlabel)
figure('Color','w');

% Reduce picture size by factor 1.5
set(gcf,'Units','pixels');
pos = get(gcf,'Position');
set(gcf,'Position',[pos(1) pos(2) round(pos(3)/1.5) round(pos(4)/1.5)]);

fs = 16;

hold on
p1 = plot(Year, Y(:,1), 'k-',  'LineWidth', 1.8);
p2 = plot(Year, Y(:,2), 'k--', 'LineWidth', 1.8);

grid on
box off

ax = gca;
set(ax, ...
    'TickLabelInterpreter','latex', ...
    'FontSize', fs, ...
    'LineWidth', 1, ...
    'XMinorTick','on', ...
    'YMinorTick','on');

% X label: TeX font (Times), same size
xlabel('Année de naissance', ...
    'Interpreter','tex', ...
    'FontName','Times New Roman', ...
    'FontSize', fs);

% Limits
xlim([Year(1) Year(end)]);

% Force y-axis to start at zero (and ensure tick labels include 0)
yl = ylim;
ylim([0 yl(2)]);
yticks(unique([0 yticks]));

% Y axis tick labels like "3,5\%"
yt = yticks;
ylab = compose('$%.1f\\%%$', 100*yt);
ylab = strrep(ylab,'.','{,}');
yticklabels(ylab);

% Legend: boxed, northeast, NOT LaTeX (avoid export bounding-box issues)
lgd = legend([p1 p2], ...
    {'Taux de rendement effectif','Taux de rendement implicite'}, ...
    'Interpreter','tex', ...          % <-- key change
    'Location','northeast', ...
    'Box','on');
lgd.FontSize = fs;
lgd.FontName = 'Times New Roman';     % optional: keep consistent look

hold off

% Export as PDF (vector)
exportgraphics(gcf,'Fig_A2_11.pdf','ContentType','vector','BackgroundColor','white');

% Optional EPS
% set(gcf,'PaperPositionMode','auto');
% print(gcf,'Fig_A2_11','-depsc2','-painters');

